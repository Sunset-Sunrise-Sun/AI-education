"""Focused independent Curriculum final invariants, synthetic/local inputs only."""
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
    assert code!=0 and payload.get('status')!='ready'


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
    assert payload['level2_eligible'] is False
