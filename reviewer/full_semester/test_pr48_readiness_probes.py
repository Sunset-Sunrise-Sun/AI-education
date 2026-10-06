"""Independent PR48 orchestration probes; all generated inputs synthetic/local."""
import copy
import json
import sqlite3
from pathlib import Path

import pytest
from test_prepare_real_case_a_runtime_cli import TOOL, _base_argv, _write_bundles


def run(capsys,args):
    code=TOOL.main(args)
    output=capsys.readouterr()
    payload=json.loads(output.out.strip() or output.err.strip())
    return code,payload


def arguments(tmp_path,bundles):
    return [*_base_argv(tmp_path,bundles=bundles),'--campus-store',str(tmp_path/'campus.sqlite'),
            '--sqlite',str(tmp_path/'accepted.sqlite')]


@pytest.fixture
def prepared(tmp_path,capsys):
    bundles=_write_bundles(tmp_path)
    argv=arguments(tmp_path,bundles)
    inventory=tmp_path/'inventory.json'
    code,payload=run(capsys,[*argv,'--draft-inventory-out',str(inventory)])
    assert code==0 and payload['acceptance_performed'] is False
    return argv,inventory,bundles


@pytest.mark.parametrize('option',['--south','--north'])
def test_missing_shard_fails_closed(tmp_path,capsys,option):
    argv=arguments(tmp_path,_write_bundles(tmp_path))
    index=argv.index(option)
    del argv[index:index+2]
    code,payload=run(capsys,[*argv,'--draft-inventory-out',str(tmp_path/'inventory.json')])
    assert code!=0 and payload['category']=='missing_shard_bundle'
    assert not (tmp_path/'accepted.sqlite').exists()


@pytest.mark.parametrize('mutation',['duplicate','conflicting','wrong-semester','baseline-drift','invalid-inventory'])
def test_reject_invalid_preparation(tmp_path,capsys,mutation):
    bundles=_write_bundles(tmp_path)
    if mutation in ('duplicate','conflicting'):
        east=json.loads(bundles['east-campus'].read_text())
        south=json.loads(bundles['south-campus'].read_text())
        if mutation=='duplicate':
            south['pages'][0]['response']['data']['rows'][0]=copy.deepcopy(east['pages'][0]['response']['data']['rows'][0])
        else:
            row=south['pages'][0]['response']['data']['rows'][0]
            source=east['pages'][0]['response']['data']['rows'][0]
            row.update(courseNum=source['courseNum'],classNumber=source['classNumber'])
        bundles['south-campus'].write_text(json.dumps(south),encoding='utf-8')
    elif mutation=='wrong-semester':
        north=json.loads(bundles['north-campus'].read_text())
        north['semester']='2027-1'
        bundles['north-campus'].write_text(json.dumps(north),encoding='utf-8')
    argv=arguments(tmp_path,bundles)
    if mutation=='baseline-drift':
        argv[argv.index('--baseline-after')+1]='11'
    inventory=tmp_path/'inventory.json'
    code,payload=run(capsys,[*argv,'--draft-inventory-out',str(inventory)])
    if code==0:
        if mutation=='invalid-inventory': inventory.write_text('{"PRIVATE-INVALID":1}')
        code,payload=run(capsys,[*argv,'--inventory',str(inventory)])
    assert code!=0, f'{mutation} accepted unexpectedly'
    assert not (tmp_path/'accepted.sqlite').exists()


def test_existing_database_default_refusal(tmp_path,capsys):
    db=tmp_path/'accepted.sqlite'
    db.write_bytes(b'KEEP')
    code,payload=run(capsys,[*arguments(tmp_path,_write_bundles(tmp_path)),
                            '--draft-inventory-out',str(tmp_path/'inventory.json')])
    assert code==TOOL.EXIT_STORE_TARGET
    assert db.read_bytes()==b'KEEP'


def test_existing_accepted_database_idempotent(prepared,tmp_path,capsys):
    argv,inventory,_=prepared
    code,first=run(capsys,[*argv,'--inventory',str(inventory)])
    assert code==0
    code,second=run(capsys,[*argv,'--inventory',str(inventory),'--allow-existing-store'])
    assert code==0 and first['acceptance']['manifest_sha256']==second['acceptance']['manifest_sha256']
    assert second['provider_read_back']['readback_member_count']==10


@pytest.mark.parametrize('mutation',['row','membership','acceptance'])
def test_tampered_readback_refused(prepared,tmp_path,capsys,mutation):
    argv,inventory,_=prepared
    code,payload=run(capsys,[*argv,'--inventory',str(inventory)])
    assert code==0
    db=tmp_path/'accepted.sqlite'
    with sqlite3.connect(db) as connection:
        if mutation=='row':connection.execute("UPDATE course_offering SET course_name='INDEPENDENT-TAMPER'")
        elif mutation=='membership':connection.execute('DELETE FROM course_data_acceptance_member')
        else:connection.execute('DELETE FROM course_data_acceptance')
    with pytest.raises(TOOL.StageFailure) as rejected:
        TOOL._provider_read_back(sqlite=db,semester='2026-1',acceptance_sha256=payload['acceptance']['manifest_sha256'],merged_offering_count=10)
    assert rejected.value.exit_code==TOOL.EXIT_PROVIDER_READBACK


def test_unrelated_provider_error_propagates(tmp_path,monkeypatch):
    def internal(*args,**kwargs): raise ValueError('independent programming defect')
    monkeypatch.setattr(TOOL,'StoreBackedCourseDataProvider',internal)
    with pytest.raises(ValueError,match='programming defect'):
        TOOL._provider_read_back(sqlite=tmp_path/'unused',semester='2026-1',acceptance_sha256='a'*64,merged_offering_count=10)


def test_env_force_must_not_destroy_verified_database(prepared,tmp_path,capsys):
    argv,inventory,_=prepared
    db=tmp_path/'accepted.sqlite'
    code,payload=run(capsys,[*argv,'--inventory',str(inventory),'--env-out',str(db),'--force'])
    assert code!=0, 'returned ready after overwriting verified SQLite with env text'
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT COUNT(*) FROM course_data_acceptance').fetchone()[0]==1


def test_env_race_default_must_not_overwrite(tmp_path,monkeypatch):
    env=tmp_path/'runtime.env'
    original=Path.exists
    def racing_exists(self):
        observed=original(self)
        if self==env and not observed:
            env.write_text('CONCURRENT=keep\n')
        return observed
    monkeypatch.setattr(Path,'exists',racing_exists)
    with pytest.raises(TOOL.StageFailure):
        TOOL._write_env_file(env,{'APP_REAL_CASE_A_ENABLED':'1'},force=False)
    assert env.read_text()=='CONCURRENT=keep\n'


def test_documented_capture_export_commands_have_a_result_binding():
    import re
    import subprocess
    runbook=TOOL.REPOSITORY_ROOT/'docs/e2e/REAL_CAPTURE_AND_RUNTIME_RUNBOOK.md'
    blocks=re.findall(r'```javascript\n(.*?)\n```',runbook.read_text(),re.S)
    assert len(blocks)>=2
    stub="const window={XuehangSysuCollector:{collectSharded:async()=>({shards:[],diagnostics:{}}),toShardJson:()=>'',toDiagnosticsJson:()=>''}};\n"
    result=subprocess.run(['node','--input-type=module','-e',stub+blocks[0]+'\n'+blocks[1]],text=True,capture_output=True)
    assert result.returncode==0, result.stderr
