"""Independent synthetic-only HTTP/stream assertions for PR #47 final review."""
import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import completed_courses as route
from app.services import completed_courses_ingest as ingest
from app.curriculum.completed_courses import normalize_completed_courses
import xlsx_fixtures as fx

PATH = '/api/v1/completed-courses/import'

@pytest.fixture
def client(monkeypatch):
    # Unexpected Mock load calls fail this test, successful XLSX uses the real loader.
    from app.services import mock_service
    def forbidden(*args, **kwargs):
        pytest.fail('XLSX fallback called a Mock loader')
    with TestClient(app, raise_server_exceptions=False) as c:
        for name in ('load_makeup_tasks', 'load_course_offerings', 'load_preference', 'load_plan_result'):
            monkeypatch.setattr(mock_service, name, forbidden)
        assert not app.dependency_overrides
        yield c


def post(client, data, headers=None):
    return client.post(PATH, content=data, headers={'Content-Type':'application/octet-stream', **(headers or {})})


def safe_error(response):
    for marker in ('REVIEW-PRIVATE', 'Traceback', '<worksheet', '<row', '/tmp/', 'completed-courses-upload-'):
        assert marker not in response.text


def test_valid_privacy_unicode_and_roundtrip(client):
    payload = fx.workbook_bytes(sheet_xml=fx.sheet_with_records([
        fx.record_row(1, course_name='独立示例课 ✓', notes='REVIEW-PRIVATE-NOTE'),
        fx.record_row(2, course_id=None, course_id_status='pending', course_name='待确认课 Ω'),
    ]))
    response = post(client, payload, {'Content-Disposition':'attachment; filename="../../REVIEW-PRIVATE.xlsx"'})
    assert response.status_code == 200
    safe_error(response)
    body=response.json()
    assert body['artifact_sha256'] == hashlib.sha256(payload).hexdigest()
    records=body['completed_input']['records']
    assert records[0]['course_name'] == '独立示例课 ✓'
    assert records[1]['course_id'] is None and records[1]['course_id_status'] == 'pending'
    assert all('notes' not in r for r in records)
    normalized = normalize_completed_courses(records, source_id=body['source_id'])
    assert len(normalized) == 2 and normalized[1].course_id is None


@pytest.mark.parametrize('kind', ['empty-bytes','empty-sheet','malformed-zip','invalid-xlsx','wrong-headers','formula','unexpected-sheet'])
def test_expected_fail_closed_inputs(client, kind):
    payloads={
        'empty-bytes':b'', 'empty-sheet':fx.empty_sheet_bytes(),
        'malformed-zip':b'PK\x03\x04REVIEW-PRIVATE-BROKEN',
        'invalid-xlsx':fx.malformed_bytes(), 'wrong-headers':fx.wrong_headers_bytes(),
        'formula':fx.formula_cell_bytes(),
        'unexpected-sheet':fx.workbook_bytes(selected_sheet_name='REVIEW-PRIVATE-WORKSHEET'),
    }
    response=post(client,payloads[kind])
    assert response.status_code == 400
    safe_error(response)


def test_duplicate_attempts_preserved(client):
    payload=fx.workbook_bytes(sheet_xml=fx.sheet_with_records([fx.record_row(1),fx.record_row(2)]))
    response=post(client,payload)
    assert response.status_code == 200
    records=response.json()['completed_input']['records']
    assert len(records)==2 and records[0]['course_id']==records[1]['course_id']
    assert records[0]['source_record'] != records[1]['source_record']


def test_duplicate_sequence_rejected(client):
    payload=fx.workbook_bytes(sheet_xml=fx.sheet_with_records([fx.record_row(1),fx.record_row(1)]))
    response=post(client,payload)
    assert response.status_code==400
    safe_error(response)


@pytest.mark.parametrize('mime',['text/plain','application/json','multipart/form-data','application/vnd.ms-excel',''])
def test_media_whitelist(client,mime):
    assert post(client,fx.valid_bytes(),{'Content-Type':mime}).status_code==415


def test_missing_content_length(client):
    r=post(client,iter([fx.valid_bytes()]))
    assert r.status_code==411


@pytest.mark.parametrize('declared,expected', [('9',400),('8388609',413),('nope',411),('-1',411),pytest.param('9'*4301,413,id='4301-digit-oversized')])
def test_declared_length_boundary_http(client,declared,expected):
    response=post(client,b'abc',{'Content-Length':declared})
    assert response.status_code==expected, f'Content-Length digits={len(declared)} returned {response.status_code}: {response.text}'
    safe_error(response)


def test_temp_cleanup_on_domain_and_internal_errors(client,monkeypatch):
    paths=[]
    original=ingest.tempfile.mkstemp
    def track(*args,**kwargs):
        fd,name=original(*args,**kwargs)
        paths.append(Path(name))
        return fd,name
    monkeypatch.setattr(ingest.tempfile,'mkstemp',track)
    assert post(client,fx.valid_bytes()).status_code==200
    assert post(client,fx.malformed_bytes()).status_code==400
    def defect(*args,**kwargs):
        raise RuntimeError('REVIEW-PRIVATE-INTERNAL')
    monkeypatch.setattr(ingest,'load_completed_courses_xlsx',defect)
    response=post(client,fx.valid_bytes())
    assert response.status_code==500
    safe_error(response)
    assert len(paths)==3 and all(not path.exists() for path in paths)


def test_macro_binary_not_read(client,monkeypatch):
    from zipfile import ZipFile
    original=ZipFile.read
    def guard(self,name,*args,**kwargs):
        resolved=getattr(name,'filename',name)
        assert not str(resolved).lower().endswith('.bin')
        return original(self,name,*args,**kwargs)
    monkeypatch.setattr(ZipFile,'read',guard)
    payload=fx.workbook_bytes(sheet_xml=fx.sheet_with_records([fx.record_row(1)]),extra_parts=fx.macro_parts())
    response=post(client,payload)
    assert response.status_code==200
    assert 'DEMO-VBA-MARKER' not in response.text


def asgi_request(headers,chunks):
    sent=[]
    reads=[]
    async def receive():
        i=len(reads)
        reads.append(i)
        return {'type':'http.request','body':chunks[i], 'more_body':i<len(chunks)-1}
    async def send(message):
        sent.append(message)
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST',
           'scheme':'http','path':PATH,'raw_path':PATH.encode(),'query_string':b'',
           'root_path':'','headers':headers,'server':('test',80),'client':('test',1234)}
    async def run():
        try:
            await app(scope,receive,send)
        except ValueError:
            # ServerErrorMiddleware sends the real 500 before re-raising to server.
            assert any(m['type']=='http.response.start' and m['status']==500 for m in sent)
    asyncio.run(run())
    status=next(m['status'] for m in sent if m['type']=='http.response.start')
    return status,reads


def test_oversized_actual_stream_stops_before_next_chunk():
    status,reads=asgi_request([(b'content-type',b'application/octet-stream'),(b'content-length',b'1')],
                              [b'a'* (4*1024*1024), b'b'*(4*1024*1024+1),b'MUST-NOT-READ'])
    assert status==413 and len(reads)==2


def test_missing_length_does_not_consume_body():
    status,reads=asgi_request([(b'content-type',b'application/octet-stream')],[b'MUST-NOT-READ'])
    assert status==411 and not reads


def test_non_ascii_digit_content_length_is_client_error():
    status,reads=asgi_request([(b'content-type',b'application/octet-stream'),(b'content-length',b'\xb2')],[b'MUST-NOT-READ'])
    assert status==411 and not reads, f'Non-ASCII digit returned HTTP {status}'
