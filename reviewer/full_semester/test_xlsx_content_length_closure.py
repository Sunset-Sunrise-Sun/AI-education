"""Focused production-boundary closure for PR #47 c904312. Synthetic only."""
import builtins
import inspect
import io
from zipfile import ZipFile, ZIP_STORED

import pytest
from app.services import completed_courses_ingest as ingest
from test_xlsx_pr47_gate import client, post, asgi_request, safe_error, fx


@pytest.mark.parametrize('value', [None, '', '１２３', '١٢٣', '²', ' 123', '123 ', '\t123', '123\t', ' ', '+123', '-1', '1.0', '1e3', '0x20', '1_000', '1,000'])
def test_invalid_length_rejected_at_parser_and_real_asgi(value):
    with pytest.raises(ingest.CompletedCoursesImportRejected) as rejected:
        ingest.parse_declared_content_length(value)
    assert rejected.value.code == ingest.ERROR_LENGTH_REQUIRED
    headers=[(b'content-type',b'application/octet-stream')]
    if value is not None:
        headers.append((b'content-length',value.encode('utf-8')))
    status, reads=asgi_request(headers,[b'MUST-NOT-READ'])
    assert status==411 and not reads


@pytest.mark.parametrize('value', ['0','1','123',str(ingest.MAX_UPLOAD_BYTES)])
def test_bounded_ascii_decimal_parser(value):
    assert ingest.parse_declared_content_length(value)==builtins.int(value)


@pytest.mark.parametrize('value', [str(ingest.MAX_UPLOAD_BYTES+1), '9'*10000, '0'*10000])
def test_oversized_decimal_real_asgi_without_integer_conversion(value,monkeypatch):
    calls=[]
    real_int=builtins.int
    def guarded_int(raw):
        assert len(raw)<=len(str(ingest.MAX_UPLOAD_BYTES)), 'unbounded int conversion reached'
        calls.append(raw)
        return real_int(raw)
    monkeypatch.setattr(ingest,'int',guarded_int,raising=False)
    headers=[(b'content-type',b'application/octet-stream'),(b'content-length',value.encode())]
    status,reads=asgi_request(headers,[b'MUST-NOT-READ'])
    assert status==413 and not reads
    if len(value)>len(str(ingest.MAX_UPLOAD_BYTES)):
        assert calls==[]


def test_valid_workbook_reaches_normal_path(client):
    response=post(client,fx.valid_bytes())
    assert response.status_code==200
    assert response.json()['record_count']==3


def test_exact_maximum_workbook_accepted(client):
    original=fx.valid_bytes()
    def build(padding):
        output=io.BytesIO()
        with ZipFile(io.BytesIO(original)) as source, ZipFile(output,'w',compression=ZIP_STORED) as target:
            for member in source.namelist():
                target.writestr(member,source.read(member))
            target.writestr('review-padding.bin',b'\x00'*padding)
        return output.getvalue()
    overhead=len(build(0))
    payload=build(ingest.MAX_UPLOAD_BYTES-overhead)
    assert len(payload)==ingest.MAX_UPLOAD_BYTES
    response=post(client,payload)
    assert response.status_code==200, response.text
    assert response.json()['record_count']==3


def test_documented_mismatch_and_invalid_workbook(client):
    response=post(client,b'abc',{'Content-Length':'4'})
    assert response.status_code==400
    assert response.json()['detail']['error']==ingest.ERROR_LENGTH_MISMATCH
    safe_error(response)
    response=post(client,b'REVIEW-PRIVATE-MALFORMED')
    assert response.status_code==400
    assert response.json()['detail']['error']==ingest.ERROR_INVALID
    safe_error(response)


def test_actual_stream_overflow_stops_reading():
    headers=[(b'content-type',b'application/octet-stream'),(b'content-length',b'1')]
    status,reads=asgi_request(headers,[b'a'*(4*1024*1024),b'b'*(4*1024*1024+1),b'MUST-NOT-READ'])
    assert status==413 and len(reads)==2


def test_rejected_headers_do_not_echo_private_values(client):
    for raw,expected in [('REVIEW-PRIVATE-HEADER',411),('9'*10000,413),(' 123 ',411)]:
        response=post(client,b'REVIEW-PRIVATE-BODY',{'Content-Length':raw})
        assert response.status_code==expected
        safe_error(response)
        assert raw not in response.text


def test_parser_explicit_ascii_digits_no_strip():
    source=inspect.getsource(ingest.parse_declared_content_length)
    # Disregard comments; check actual function AST for the requested implementation boundary.
    import ast
    tree=ast.parse(source)
    attributes=[node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)]
    assert 'isascii' in attributes and 'isdigit' in attributes and 'strip' not in attributes
