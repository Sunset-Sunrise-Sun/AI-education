"""Independent successful-mode/status probes for PR48; all fixtures synthetic/local."""
import dataclasses
import inspect
import json
from pathlib import Path

import pytest
from test_pr48_final_invariants import inputs,run,edit,TOOL


def test_verified_object_and_unchanged_ready(inputs,capsys,monkeypatch):
    argv,_,_,case,_,_=inputs
    original=TOOL._runtime_environment
    observed=[]
    def derive(*,store,curriculum):
        assert isinstance(curriculum,TOOL.VerifiedCurriculum)
        assert curriculum.resolved_path==case.resolve()
        assert dataclasses.is_dataclass(curriculum)
        with pytest.raises(dataclasses.FrozenInstanceError):curriculum.resolved_path=Path('/unverified')
        for field in ('artifact_sha256','case_id','target_version_id','curriculum_format',
                      'curriculum_format_version','approved_by','approved_at','synthetic'):
            assert hasattr(curriculum,field)
        observed.append(curriculum)
        return original(store=store,curriculum=curriculum)
    monkeypatch.setattr(TOOL,'_runtime_environment',derive)
    code,payload=run(capsys,argv)
    assert code==0 and payload['status']=='ready' and payload['level2_eligible']
    final=payload['final_readiness_verification']
    assert final['final_store_reverified'] is True and final['final_curriculum_reverified'] is True
    assert len(observed)==1
    assert set(inspect.signature(original).parameters)=={'store','curriculum'}


@pytest.mark.parametrize('attack',['replace','delete','redirect-env','directory',
    'symlink-rebind','directory-rebind','store-invalid','approval-invalid'])
def test_post_publication_attack_no_ready(inputs,capsys,monkeypatch,tmp_path,attack):
    argv,db,env,case,_,_=inputs
    original=TOOL._write_env_file
    def publish_then_attack(path,environment):
        original(path,environment)
        if attack=='replace': case.write_bytes(b'INDEPENDENT CHANGED BYTES')
        elif attack=='delete':case.unlink()
        elif attack=='directory':case.unlink();case.mkdir()
        elif attack in ('symlink-rebind','directory-rebind'):
            other=tmp_path/'new-target';other.mkdir()
            (other/'case.json').write_bytes(case.read_bytes())
            if attack=='symlink-rebind':
                case.unlink();case.symlink_to(other/'case.json')
            else:
                parent=tmp_path/'rebound';parent.mkdir()
                target=parent/'case.json';target.write_bytes(case.read_bytes())
                env.write_text(env.read_text().replace(str(case),str(target)))
                moved=tmp_path/'old-parent';parent.rename(moved);parent.symlink_to(other,target_is_directory=True)
        elif attack=='redirect-env':
            other=tmp_path/'other.json';other.write_bytes(case.read_bytes())
            env.write_text(env.read_text().replace(str(case),str(other)))
        elif attack=='store-invalid':db.write_bytes(b'CORRUPTED STORE')
    monkeypatch.setattr(TOOL,'_write_env_file',publish_then_attack)
    if attack=='approval-invalid':
        final=TOOL._final_readiness_verification
        def invalidate(**kwargs):
            kwargs['curriculum']=dataclasses.replace(kwargs['curriculum'],approved_at='no timezone')
            return final(**kwargs)
        monkeypatch.setattr(TOOL,'_final_readiness_verification',invalidate)
    code,payload=run(capsys,argv)
    assert code!=0 and payload.get('status') not in ('ready','partial_ready')


@pytest.mark.parametrize('invalid',['course-data','curriculum','missing-provenance'])
def test_combined_gate_and_no_unverified_case_emission(inputs,capsys,invalid):
    argv,_,env,_,handoff,provenance=inputs
    if invalid=='course-data':edit(handoff,'approved_by','')
    elif invalid=='curriculum':edit(provenance,'curriculum_artifact_sha256','f'*64)
    else:
        index=argv.index('--curriculum-provenance');del argv[index:index+2]
    code,payload=run(capsys,argv)
    assert code!=0 or payload['level2_eligible'] is False
    if invalid!='course-data':
        assert 'APP_CASE_A_CURRICULUM_CASE_PATH' not in TOOL._read_env_bindings(env)


def test_ready_always_requires_both_final_reverifications(inputs,capsys):
    argv,*_=inputs
    index=argv.index('--curriculum-provenance');del argv[index:index+2]
    code,payload=run(capsys,argv)
    assert code!=0 or payload.get('status')!='ready' or (
        payload['final_readiness_verification']['final_store_reverified'] is True and
        payload['final_readiness_verification']['final_curriculum_reverified'] is True
    ), 'status ready returned without final Curriculum reverification'


def test_synthetic_preflight_level1(capsys):
    code,payload=run(capsys,['--preflight','--quiet'])
    assert code==0 and payload['level']=='LEVEL1-synthetic-preflight'
    assert payload['status']=='partial_ready'
    assert payload['readiness_scope']=='course_data_only'
    assert payload['level2_eligible'] is False


CONFIG_KEYS={'APP_COURSE_DATA_SQLITE_PATH','APP_COURSE_DATA_SEMESTER',
             'APP_COURSE_DATA_ACCEPTANCE_SHA256','APP_CASE_A_CURRICULUM_CASE_PATH'}


def ready_property(payload):
    if payload.get('status')=='ready':
        final=payload['final_readiness_verification']
        assert final['final_store_reverified'] is True
        assert final['final_curriculum_reverified'] is True
        assert CONFIG_KEYS<=set(payload['runtime_environment'])


@pytest.mark.parametrize('mode',['full-env','full-no-env','partial','partial-no-case',
    'draft-inventory','draft-handoff','draft-curriculum','draft-all','preflight'])
def test_all_successful_modes_global_property(inputs,capsys,tmp_path,mode):
    argv,db,env,case,handoff,provenance=inputs
    if mode=='preflight':args=['--preflight','--quiet']
    else:
        args=list(argv)
        if mode=='full-no-env':
            i=args.index('--env-out');del args[i:i+2]
        if mode.startswith('partial'):
            i=args.index('--curriculum-provenance');del args[i:i+2]
            if mode=='partial-no-case':
                i=args.index('--curriculum-case');del args[i:i+2]
        if mode.startswith('draft'):
            for option in ('--inventory','--handoff','--curriculum-provenance','--env-out'):
                i=args.index(option);del args[i:i+2]
            choices={'draft-inventory':['inventory'],'draft-handoff':['handoff'],
                     'draft-curriculum':['curriculum-provenance'],
                     'draft-all':['inventory','handoff','curriculum-provenance']}[mode]
            if 'inventory' not in choices:args += ['--inventory',argv[argv.index('--inventory')+1]]
            for kind in choices:args += ['--draft-'+kind+'-out',str(tmp_path/('new-'+kind+'.json'))]
            if 'curriculum-provenance' in choices:
                args += ['--curriculum-case-id','case-a','--curriculum-target-version-id','case-a-new',
                    '--curriculum-applicable-term','2025-2','--curriculum-format','sysu-curriculum-case-v1',
                    '--curriculum-format-version','1']
    code,payload=run(capsys,args)
    assert code==0,payload
    ready_property(payload)
    if mode.startswith('full'):
        assert payload['status']=='ready' and payload['level2_eligible'] is True
    elif mode in ('draft-inventory','draft-all'):
        assert payload['status'] not in ('ready','partial_ready')
        assert payload['acceptance_performed'] is False
    else:
        assert payload['status']=='partial_ready'
        assert payload['readiness_scope']=='course_data_only'
        assert payload['level2_eligible'] is False
        assert payload['final_readiness_verification']['final_store_reverified'] is True
        assert payload['final_readiness_verification']['final_curriculum_reverified'] is False
        assert 'APP_CASE_A_CURRICULUM_CASE_PATH' not in payload['runtime_environment']
        assert any('DO NOT launch' in step for step in payload['next_steps'])
        if mode!='preflight':assert 'curriculum_provenance_missing' in payload['level2_blockers']


@pytest.mark.parametrize('broken',['store-false','curriculum-false','store-int',
    'curriculum-missing','db-path-missing','case-path-missing'])
def test_require_ready_invariant_fail_closed(broken):
    final={'final_store_reverified':True,'final_curriculum_reverified':True}
    env={key:'INDEPENDENT' for key in CONFIG_KEYS}
    if broken=='store-false':final['final_store_reverified']=False
    elif broken=='curriculum-false':final['final_curriculum_reverified']=False
    elif broken=='store-int':final['final_store_reverified']=1
    elif broken=='curriculum-missing':del final['final_curriculum_reverified']
    elif broken=='db-path-missing':del env['APP_COURSE_DATA_SQLITE_PATH']
    else:del env['APP_CASE_A_CURRICULUM_CASE_PATH']
    with pytest.raises(TOOL.StageFailure):
        TOOL._require_ready_invariant(status='ready',final_verification=final,environment=env)


def test_invariant_enforced_when_python_asserts_disabled():
    import subprocess,sys,os
    script="""from test_prepare_real_case_a_runtime_cli import TOOL
try:
 TOOL._require_ready_invariant(status='ready',final_verification={'final_store_reverified':True,'final_curriculum_reverified':False},environment={})
except TOOL.StageFailure:
 print('GUARD_ENFORCED')
else:
 raise RuntimeError('ready guard bypassed with -O')
"""
    result=subprocess.run([sys.executable,'-O','-c',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='GUARD_ENFORCED'
