"""Independent actual CLI probes for PR48 final closure; local synthetic inputs only."""
import hashlib
import inspect
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from test_prepare_real_case_a_runtime_cli import TOOL, _base_argv, _write_bundles
from test_synthetic_production_e2e import _case_payload
from app.services.planning_runtime import build_planning_runtime


def run(capsys,args):
    code=TOOL.main(args)
    captured=capsys.readouterr()
    return code,json.loads(captured.out.strip() or captured.err.strip())


@pytest.fixture
def inputs(tmp_path,capsys):
    bundles=_write_bundles(tmp_path)
    db=tmp_path/'accepted.sqlite'
    env=tmp_path/'runtime.env'
    case=tmp_path/'case.json'
    case.write_text(json.dumps(_case_payload()),encoding='utf-8')
    inventory=tmp_path/'inventory.json'
    handoff=tmp_path/'handoff.json'
    argv=[*_base_argv(tmp_path,bundles=bundles),'--campus-store',str(tmp_path/'campus.sqlite'),
          '--sqlite',str(db)]
    code,payload=run(capsys,[*argv,'--draft-inventory-out',str(inventory),
                           '--draft-handoff-out',str(handoff)])
    assert code==0 and not payload['acceptance_performed']
    h=json.loads(handoff.read_text())
    h.update(handoff_state='approved',approved_by='independent-local-review',
             approved_at='2026-10-06T20:00:00+08:00')
    handoff.write_text(json.dumps(h))
    provenance=tmp_path/'provenance.json'
    p={'curriculum_provenance_format':'sysu-real-curriculum-provenance-v1',
       'curriculum_provenance_version':1,'curriculum_source_kind':'case_a_approved_case_json',
       'curriculum_case_id':'case-a','curriculum_target_version_id':'case-a-new',
       'curriculum_applicable_term':'2025-2',
       'curriculum_artifact_sha256':hashlib.sha256(case.read_bytes()).hexdigest(),
       'curriculum_format':'sysu-curriculum-case-v1','curriculum_format_version':'1',
       'loader_commit':'independent-test','synthetic':False,'approval_state':'approved',
       'approved_by':'independent-local-review','approved_at':'2026-10-06T20:00:00+08:00',
       'approval_note':None}
    provenance.write_text(json.dumps(p))
    argv += ['--inventory',str(inventory),'--handoff',str(handoff),
             '--curriculum-provenance',str(provenance),'--curriculum-case',str(case),
             '--env-out',str(env)]
    return argv,db,env,case,handoff,provenance


def edit(path,field,value):
    p=json.loads(path.read_text()); p[field]=value; path.write_text(json.dumps(p))


def assert_ineligible(code,payload):
    assert code!=0 or payload.get('level2_eligible') is False, payload


@pytest.mark.parametrize('option',['--overwrite-env','--force','--overwrite'])
def test_no_overwrite_cli_option(capsys,option):
    code,payload=run(capsys,['--preflight',option])
    assert code!=0 and payload.get('status')!='ready'
    assert option not in TOOL._build_parser()._option_string_actions


@pytest.mark.parametrize('destination',['existing-env','accepted-db'])
def test_existing_env_destination_unchanged(inputs,capsys,destination):
    argv,db,env,*_=inputs
    if destination=='existing-env':
        env.write_bytes(b'KEEP-INDEPENDENT\n'); target=env
    else:
        target=db; argv[argv.index('--env-out')+1]=str(db)
    code,payload=run(capsys,argv)
    assert code!=0 and payload.get('status')!='ready'
    if target==env: assert env.read_bytes()==b'KEEP-INDEPENDENT\n'
    else:
        with sqlite3.connect(db) as conn:
            assert conn.execute('SELECT COUNT(*) FROM course_data_acceptance').fetchone()[0]==1


def test_env_verified_store_and_post_publish_readback(inputs,capsys,monkeypatch):
    argv,db,env,case,*_=inputs
    original=TOOL._provider_read_back
    events=[]
    def observed(**kwargs):
        events.append((env.exists(),Path(kwargs['sqlite']),kwargs['acceptance_sha256']))
        return original(**kwargs)
    monkeypatch.setattr(TOOL,'_provider_read_back',observed)
    code,payload=run(capsys,argv)
    assert code==0 and payload['level2_eligible'] is True
    bindings=TOOL._read_env_bindings(env)
    assert Path(bindings['APP_COURSE_DATA_SQLITE_PATH']).resolve()==db.resolve()
    sha=payload['acceptance']['manifest_sha256']
    assert bindings['APP_COURSE_DATA_ACCEPTANCE_SHA256']==sha
    assert events==[(False,db.resolve(),sha),(True,db.resolve(),sha)]
    assert bindings['APP_CASE_A_CURRICULUM_CASE_PATH']==str(case.resolve())
    with sqlite3.connect(db) as conn:
        manifest=conn.execute('SELECT canonical_manifest_json FROM course_data_acceptance').fetchone()[0]
    assert hashlib.sha256(manifest.encode()).hexdigest()==sha
    assert set(inspect.signature(TOOL._runtime_environment).parameters)=={'store','curriculum_case'}


@pytest.mark.parametrize('attack',['row','membership','delete-acceptance','corrupt-db','delete-db','env-path','env-sha'])
def test_mutation_after_publication_never_ready(inputs,capsys,monkeypatch,attack):
    argv,db,env,*_=inputs
    original=TOOL._write_env_file
    def publish_then_mutate(path,environment):
        original(path,environment)
        if attack=='corrupt-db': db.write_bytes(b'INDEPENDENT-CORRUPTION')
        elif attack=='delete-db': db.unlink()
        elif attack.startswith('env-'):
            text=env.read_text()
            old=str(db.resolve()) if attack=='env-path' else environment['APP_COURSE_DATA_ACCEPTANCE_SHA256']
            new=str(db.parent/'other.sqlite') if attack=='env-path' else 'a'*64
            env.write_text(text.replace(old,new))
        else:
            with sqlite3.connect(db) as conn:
                if attack=='row':conn.execute("UPDATE course_offering SET course_name='INDEPENDENT-CHANGED'")
                elif attack=='membership':conn.execute('DELETE FROM course_data_acceptance_member')
                else:conn.execute('DELETE FROM course_data_acceptance')
    monkeypatch.setattr(TOOL,'_write_env_file',publish_then_mutate)
    code,payload=run(capsys,argv)
    assert code!=0 and payload.get('status')!='ready'


@pytest.mark.parametrize('field,value',[
    ('approved_by',''),('approved_by','   '),('approved_at',''),
    ('approved_at','not-a-date'),('approved_at','2026-10-06T20:00:00'),
    ('synthetic',True),('handoff_state','draft')])
def test_handoff_matrix(inputs,capsys,field,value):
    argv,_,_,_,handoff,_=inputs
    edit(handoff,field,value)
    assert_ineligible(*run(capsys,argv))


@pytest.mark.parametrize('attack',[
    'missing-provenance','missing-digest','malformed-digest','wrong-digest','synthetic',
    'unapproved','empty-by','blank-by','empty-at','malformed-at','naive-at',
    'missing-case-option','missing-case-file','wrong-case','wrong-format','wrong-version'])
def test_curriculum_matrix(inputs,capsys,tmp_path,attack):
    argv,_,_,case,_,provenance=inputs
    if attack in ('missing-provenance','missing-case-option'):
        option='--curriculum-provenance' if attack=='missing-provenance' else '--curriculum-case'
        index=argv.index(option); del argv[index:index+2]
    elif attack=='missing-case-file':
        case.unlink()
        result=subprocess.run([sys.executable,str(TOOL.REPOSITORY_ROOT/'tools/prepare_real_case_a_runtime.py'),*argv],capture_output=True,text=True)
        assert result.returncode!=0 and '"status": "ready"' not in result.stdout
        return
    elif attack=='wrong-case':
        other=tmp_path/'other-case.json';other.write_bytes(b'{"synthetic":"source B"}')
        argv[argv.index('--curriculum-case')+1]=str(other)
    elif attack=='missing-digest':
        p=json.loads(provenance.read_text());del p['curriculum_artifact_sha256'];provenance.write_text(json.dumps(p))
    else:
        field,value={
            'malformed-digest':('curriculum_artifact_sha256','not-sha'),
            'wrong-digest':('curriculum_artifact_sha256','f'*64),
            'synthetic':('synthetic',True),'unapproved':('approval_state','draft'),
            'empty-by':('approved_by',''),'blank-by':('approved_by','   '),
            'empty-at':('approved_at',''),'malformed-at':('approved_at','not-a-date'),
            'naive-at':('approved_at','2026-10-06T20:00:00'),
            'wrong-format':('curriculum_provenance_format','unknown'),
            'wrong-version':('curriculum_provenance_version',999)}[attack]
        edit(provenance,field,value)
    assert_ineligible(*run(capsys,argv))


def test_preflight_is_only_level1(capsys):
    code,payload=run(capsys,['--preflight','--quiet'])
    assert code==0 and payload['level']=='LEVEL1-synthetic-preflight'
    assert payload['synthetic'] is True and payload['level2_eligible'] is False


@pytest.mark.parametrize('attack',['replace-case-bytes','redirect-emitted-case-path'])
def test_final_curriculum_provenance_matches_emitted_runtime_input(inputs,capsys,monkeypatch,tmp_path,attack):
    argv,_,env,case,_,provenance=inputs
    approved_digest=json.loads(provenance.read_text())['curriculum_artifact_sha256']
    original=TOOL._write_env_file
    def publish_then_mutate(path,environment):
        original(path,environment)
        changed=json.loads(case.read_text())
        changed['new']['course_records'][0]['course_name']='INDEPENDENT UNAPPROVED PAYLOAD'
        if attack=='replace-case-bytes':
            case.write_text(json.dumps(changed))
        else:
            other=tmp_path/'unapproved-case.json'
            other.write_text(json.dumps(changed))
            env.write_text(env.read_text().replace(str(case.resolve()),str(other.resolve())))
    monkeypatch.setattr(TOOL,'_write_env_file',publish_then_mutate)
    code,payload=run(capsys,argv)
    emitted=TOOL._read_env_bindings(env)
    consumed_path=Path(emitted['APP_CASE_A_CURRICULUM_CASE_PATH'])
    assert hashlib.sha256(consumed_path.read_bytes()).hexdigest()!=approved_digest
    assert build_planning_runtime(emitted).reason=='ready', 'probe must demonstrate actual runtime-consumable replacement'
    assert code!=0 or payload.get('level2_eligible') is False, 'unapproved emitted Curriculum input authorized LEVEL2'
