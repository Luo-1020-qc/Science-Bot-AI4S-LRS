"""Meaningful tamper checks for historical and chained source protections."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import integrity as guard


def checksum(content): return hashlib.sha256(content).hexdigest()


class ChainedIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.hosts = guard.TOOL_HOST_FILES|guard.PLANNING_HOST_FILES
        self.base = {}
        for name in self.hosts|guard.PROVIDER_FILES|{"saved/policy.json"}:
            self.put(name, b"original "+name.encode())
            self.base[name] = guard.sha(self.root/name)
        self.put_json("docs/cleanup/2026-10-28/protected_current.json", {"sha256":self.base})
        old = {}
        for name in guard.TOOL_HOST_FILES:
            self.put(name,b"tool integration "+name.encode())
            old[name] = {"before_sha256":self.base[name],"sha256":guard.sha(self.root/name),"reason":"explicit tool integration"}
        self.put_json(guard.TOOL_RECORD+"/authorized_source_changes.json",{"files":old})
        self.runtime = {name:guard.sha(self.root/name) for name in guard.TOOL_HOST_FILES}
        self.put("Research_Tool_Library/core.py", b"fixed mathematical tool")
        self.runtime["Research_Tool_Library/core.py"] = guard.sha(self.root/"Research_Tool_Library/core.py")
        self.put_json(guard.TOOL_RECORD+"/runtime_manifest.json", {"sha256":self.runtime})

    def put(self,name,data):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)

    def put_json(self,name,value): self.put(name,json.dumps(value).encode())

    def upgrade(self):
        prior=guard.effective_hashes(self.root)
        constraints={"docs/cleanup/2026-10-28/protected_current.json",guard.TOOL_RECORD+"/authorized_source_changes.json",
                     guard.TOOL_RECORD+"/runtime_manifest.json"}|guard.PROVIDER_FILES
        snapshot={"version":"planning_upgrade_before_v1","files":{name:{"before_sha256":prior[name]} for name in guard.PLANNING_HOST_FILES},
                  "unchanged_history_and_provider":{name:guard.sha(self.root/name) for name in constraints}}
        self.put_json(guard.PLANNING_RECORD+"/before_snapshot.json",snapshot)
        changes={}
        for name in guard.PLANNING_HOST_FILES:
            self.put(name,b"new planning host "+name.encode())
            changes[name]={"before_sha256":prior[name],"sha256":guard.sha(self.root/name),"reason":"explicit user planning upgrade"}
        self.put_json(guard.PLANNING_RECORD+"/authorized_source_changes.json",{"files":changes})
        for name in guard.PLANNING_NEW_FILES:self.put(name,b"new planning module "+name.encode())
        runtime={name:guard.sha(self.root/name) for name in guard.PLANNING_HOST_FILES|guard.PLANNING_NEW_FILES|guard.PROVIDER_FILES}
        self.put_json(guard.PLANNING_RECORD+"/runtime_manifest.json",{"sha256":runtime})
        return changes

    def test_old_baseline_without_new_integration(self):
        result=guard.check_project(self.root)
        self.assertTrue(result["passed"])
        self.assertEqual(result["planning_runtime_files_checked"],0)

    def test_chained_upgrade_preserves_old_runtime_history(self):
        old=(self.root/(guard.TOOL_RECORD+"/runtime_manifest.json")).read_bytes()
        self.upgrade();result=guard.check_project(self.root)
        self.assertEqual(result["authorized_host_changes"],5)
        self.assertEqual(result["planning_authorized_host_changes"],4)
        self.assertEqual(result["planning_runtime_files_checked"],11)
        self.assertEqual(old,(self.root/(guard.TOOL_RECORD+"/runtime_manifest.json")).read_bytes())

    def dynamic_upgrade(self):
        self.upgrade(); prior=guard.effective_hashes(self.root)
        before={'version':'dynamic_clarification_before_v1',
            'files':{name:prior[name] for name in guard.DYNAMIC_CHANGED_FILES},
            'unchanged_history_and_provider':{name:guard.sha(self.root/name) for name in guard.DYNAMIC_HISTORY}}
        self.put_json(guard.DYNAMIC_RECORD+'/before_snapshot.json',before)
        changes={}
        for name in guard.DYNAMIC_CHANGED_FILES:
            self.put(name,b'dynamic clarification '+name.encode())
            changes[name]={'before_sha256':prior[name],'sha256':guard.sha(self.root/name),'reason':'explicit dynamic clarification upgrade'}
        self.put_json(guard.DYNAMIC_RECORD+'/authorized_source_changes.json',{'files':changes})
        for name in guard.DYNAMIC_NEW_FILES:self.put(name,b'new read-only planning module '+name.encode())
        runtime={name:guard.sha(self.root/name) for name in guard.DYNAMIC_CHANGED_FILES|guard.DYNAMIC_NEW_FILES}
        self.put_json(guard.DYNAMIC_RECORD+'/runtime_manifest.json',{'sha256':runtime})
        return changes

    def test_dynamic_chain_keeps_previous_planning_manifest_immutable(self):
        self.dynamic_upgrade();result=guard.check_project(self.root)
        self.assertEqual(result['dynamic_runtime_files_checked'],6)
        self.assertEqual(result['planning_runtime_files_checked'],11)

    def test_dynamic_source_tamper_fails(self):
        self.dynamic_upgrade();self.put(next(iter(guard.DYNAMIC_NEW_FILES)),b'tampered')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_dynamic_overlay_cannot_change_weights(self):
        changes=self.dynamic_upgrade()
        changes['saved/policy.json']={'before_sha256':self.base['saved/policy.json'],'sha256':self.base['saved/policy.json'],'reason':'out of scope'}
        self.put_json(guard.DYNAMIC_RECORD+'/authorized_source_changes.json',{'files':changes})
        with self.assertRaisesRegex(ValueError,'exceeds authorized'):guard.check_project(self.root)

    def test_dynamic_upgrade_cannot_rewrite_old_planning_manifest(self):
        self.dynamic_upgrade();path=guard.PLANNING_RECORD+'/runtime_manifest.json'
        content=json.loads((self.root/path).read_text());content['rewritten']=True;self.put_json(path,content)
        with self.assertRaisesRegex(ValueError,'Prior planning/history/API'):guard.check_project(self.root)

    def privacy_upgrade(self):
        self.dynamic_upgrade();prior=guard.effective_hashes(self.root)
        self.put_json(guard.PRIVACY_RECORD+'/before_snapshot.json',{
            'version':'planning_history_privacy_before_v1','file':guard.PRIVACY_HOST,
            'before_sha256':prior[guard.PRIVACY_HOST],
            'dynamic_runtime_manifest_sha256':guard.sha(self.root/guard.DYNAMIC_RECORD/'runtime_manifest.json')})
        self.put(guard.PRIVACY_HOST,b'privacy-safe planning history')
        changes={guard.PRIVACY_HOST:{'before_sha256':prior[guard.PRIVACY_HOST],
            'sha256':guard.sha(self.root/guard.PRIVACY_HOST),'reason':'explicit paper sharing boundary'}}
        self.put_json(guard.PRIVACY_RECORD+'/authorized_source_changes.json',{'files':changes})
        return changes

    def test_history_privacy_source_chains_after_dynamic_upgrade(self):
        self.privacy_upgrade();result=guard.check_project(self.root)
        self.assertEqual(result['planning_history_privacy_files_checked'],1)
        self.put(guard.PRIVACY_HOST,b'tampered history')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_history_privacy_overlay_cannot_edit_provider(self):
        changes=self.privacy_upgrade();name=next(iter(guard.PROVIDER_FILES))
        changes[name]={'before_sha256':self.base[name],'sha256':self.base[name],'reason':'out of scope'}
        self.put_json(guard.PRIVACY_RECORD+'/authorized_source_changes.json',{'files':changes})
        with self.assertRaisesRegex(ValueError,'exceeds authorized'):guard.check_project(self.root)

    def interface_upgrade(self):
        self.privacy_upgrade();prior=guard.effective_hashes(self.root)
        for name in guard.INTERFACE_HOST_FILES:
            if not (self.root/name).exists():self.put(name,b'prior launch metadata '+name.encode())
        files={name:guard.sha(self.root/name) for name in guard.INTERFACE_HOST_FILES}
        history={p.relative_to(self.root).as_posix():guard.sha(p) for p in (self.root/'docs/integration').rglob('*.json')}
        self.put_json(guard.INTERFACE_RECORD+'/before_snapshot.json',{'version':'interfaces_before_v1',
            'files':{n:h for n,h in files.items() if n!='.gitignore'},'unchanged_history':history,
            'provider_and_configuration':{n:guard.sha(self.root/n) for n in guard.PROVIDER_FILES}})
        self.put_json(guard.INTERFACE_RECORD+'/before_packaging.json',{'version':'interfaces_packaging_before_v1','files':{'.gitignore':files['.gitignore']}})
        changes={}
        for name in guard.INTERFACE_HOST_FILES:
            self.put(name,b'interface entry '+name.encode())
            changes[name]={'before_sha256':files[name],'sha256':guard.sha(self.root/name),'reason':'interface example request'}
        for name in guard.INTERFACE_NEW_FILES:self.put(name,b'interface asset '+name.encode())
        self.put_json(guard.INTERFACE_RECORD+'/authorized_source_changes.json',{'files':changes})
        self.put_json(guard.INTERFACE_RECORD+'/runtime_manifest.json',{'sha256':{
            name:guard.sha(self.root/name) for name in guard.INTERFACE_HOST_FILES|guard.INTERFACE_NEW_FILES}})
        return changes

    def test_interface_layer_preserves_old_history_and_detects_asset_tamper(self):
        self.interface_upgrade();result=guard.check_project(self.root)
        self.assertEqual(result['interface_runtime_files_checked'],11)
        self.put(next(iter(guard.INTERFACE_NEW_FILES)),b'changed asset')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_interface_layer_cannot_cover_weight_changes(self):
        changes=self.interface_upgrade()
        changes['saved/policy.json']={'before_sha256':self.base['saved/policy.json'],'sha256':self.base['saved/policy.json'],'reason':'out of scope'}
        self.put_json(guard.INTERFACE_RECORD+'/authorized_source_changes.json',{'files':changes})
        with self.assertRaisesRegex(ValueError,'exceeds authorized'):guard.check_project(self.root)

    def test_interface_layer_rejects_rewritten_prior_receipt(self):
        self.interface_upgrade();name=guard.DYNAMIC_RECORD+'/runtime_manifest.json'
        old=json.loads((self.root/name).read_text());old['rebased']=True;self.put_json(name,old)
        with self.assertRaises(ValueError):guard.check_project(self.root)

    def question_upgrade(self):
        self.interface_upgrade();prior=guard.effective_hashes(self.root)
        history={p.relative_to(self.root).as_posix():guard.sha(p) for p in (self.root/'docs/integration').rglob('*.json')}
        self.put_json(guard.QUESTION_RECORD+'/before_snapshot.json',{'version':'question_tool_before_v1',
            'files':{n:prior[n] for n in guard.QUESTION_HOST_FILES},'unchanged_history':history,
            'provider_and_configuration':{n:guard.sha(self.root/n) for n in guard.PROVIDER_FILES}})
        changes={}
        for name in guard.QUESTION_HOST_FILES:
            self.put(name,b'question tool wiring '+name.encode())
            changes[name]={'before_sha256':prior[name],'sha256':guard.sha(self.root/name),'reason':'user authorized trainable question tool'}
        for name in guard.QUESTION_NEW_FILES|guard.QUESTION_TRAINING_FILES:self.put(name,b'question artifact '+name.encode())
        self.put_json(guard.QUESTION_RECORD+'/authorized_source_changes.json',{'files':changes})
        self.put_json(guard.QUESTION_RECORD+'/runtime_manifest.json',{'sha256':{n:guard.sha(self.root/n) for n in guard.QUESTION_HOST_FILES|guard.QUESTION_NEW_FILES}})
        self.put_json(guard.QUESTION_RECORD+'/training_manifest.json',{'sha256':{n:guard.sha(self.root/n) for n in guard.QUESTION_TRAINING_FILES}})
        return changes

    def test_question_tool_chains_and_detects_candidate_weight_tampering(self):
        self.question_upgrade();result=guard.check_project(self.root)
        self.assertEqual(result['question_tool_runtime_files_checked'],6)
        self.put('RUT_Science/rut_science/science_bot/general/planning/question_policy.json',b'tampered')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_question_tool_cannot_rewrite_original_weights_or_history(self):
        changes=self.question_upgrade()
        changes['saved/policy.json']={'before_sha256':self.base['saved/policy.json'],'sha256':self.base['saved/policy.json'],'reason':'out of scope'}
        self.put_json(guard.QUESTION_RECORD+'/authorized_source_changes.json',{'files':changes})
        with self.assertRaisesRegex(ValueError,'exceeds authorized'):guard.check_project(self.root)

    def test_question_training_inputs_and_prior_interface_receipts_are_protected(self):
        self.question_upgrade();name=guard.INTERFACE_RECORD+'/runtime_manifest.json'
        old=json.loads((self.root/name).read_text());old['rewritten']=True;self.put_json(name,old)
        with self.assertRaisesRegex(ValueError,'prior evidence'):guard.check_project(self.root)

    def branding_upgrade(self):
        self.question_upgrade();prior=guard.effective_hashes(self.root)
        for name in guard.BRANDING_FILES:
            if not (self.root/name).exists():self.put(name,b'previous generated preview')
        history={p.relative_to(self.root).as_posix():guard.sha(p) for p in (self.root/'docs/integration').rglob('*.json')}
        files={n:guard.sha(self.root/n) for n in guard.BRANDING_FILES}
        self.put_json(guard.BRANDING_RECORD+'/before_snapshot.json',{'version':'branding_before_v1','files':files,'unchanged_history':history})
        changes={}
        for name in guard.BRANDING_FILES:
            self.put(name,b'red presentation '+name.encode())
            changes[name]={'before_sha256':files[name],'sha256':guard.sha(self.root/name),'reason':'requested red branding'}
        self.put_json(guard.BRANDING_RECORD+'/authorized_source_changes.json',{'files':changes})
        self.put_json(guard.BRANDING_RECORD+'/runtime_manifest.json',{'sha256':{n:guard.sha(self.root/n) for n in guard.BRANDING_FILES}})
        return changes

    def test_branding_chains_and_detects_stylesheet_tampering(self):
        self.branding_upgrade();self.assertEqual(guard.check_project(self.root)['branding_files_checked'],5)
        self.put('RUT_Science/rut_science/science_bot/workbench_assets/dist/styles.css',b'changed css')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_branding_cannot_authorize_planning_engine_changes(self):
        changes=self.branding_upgrade();name='RUT_Science/rut_science/science_bot/general/planning/runtime.py'
        changes[name]={'before_sha256':guard.sha(self.root/name),'sha256':guard.sha(self.root/name),'reason':'out of visual scope'}
        self.put_json(guard.BRANDING_RECORD+'/authorized_source_changes.json',{'files':changes})
        with self.assertRaisesRegex(ValueError,'exceeds authorized'):guard.check_project(self.root)

    def test_branding_preserves_question_tool_receipts(self):
        self.branding_upgrade();name=guard.QUESTION_RECORD+'/training_manifest.json'
        old=json.loads((self.root/name).read_text());old['rewritten']=True;self.put_json(name,old)
        with self.assertRaisesRegex(ValueError,'prior evidence'):guard.check_project(self.root)

    def choices_upgrade(self):
        self.branding_upgrade();prior=guard.effective_hashes(self.root)
        history={p.relative_to(self.root).as_posix():guard.sha(p) for p in (self.root/'docs/integration').rglob('*.json')}
        self.put_json(guard.CHOICES_RECORD+'/before_snapshot.json',{'version':'context_choices_before_v1',
            'files':{n:prior[n] for n in guard.CHOICES_HOST_FILES},'unchanged_history':history})
        changes={}
        for name in guard.CHOICES_HOST_FILES:
            self.put(name,b'contextual choices '+name.encode())
            changes[name]={'before_sha256':prior[name],'sha256':guard.sha(self.root/name),'reason':'user requested selectable questions'}
        for name in guard.CHOICES_NEW_FILES|guard.CHOICES_TRAINING_FILES:self.put(name,b'choice artifact '+name.encode())
        self.put_json(guard.CHOICES_RECORD+'/authorized_source_changes.json',{'files':changes})
        self.put_json(guard.CHOICES_RECORD+'/runtime_manifest.json',{'sha256':{n:guard.sha(self.root/n) for n in guard.CHOICES_HOST_FILES|guard.CHOICES_NEW_FILES}})
        self.put_json(guard.CHOICES_RECORD+'/training_manifest.json',{'sha256':{n:guard.sha(self.root/n) for n in guard.CHOICES_TRAINING_FILES}})
        return changes

    def test_context_choices_runtime_and_trained_policy_are_protected(self):
        self.choices_upgrade();self.assertEqual(guard.check_project(self.root)['context_choices_runtime_files_checked'],11)
        self.put('RUT_Science/rut_science/science_bot/general/planning/choice_policy.json',b'tampered')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_context_choices_cannot_cover_old_training_weight_changes(self):
        changes=self.choices_upgrade()
        changes['saved/policy.json']={'before_sha256':self.base['saved/policy.json'],'sha256':self.base['saved/policy.json'],'reason':'out of scope'}
        self.put_json(guard.CHOICES_RECORD+'/authorized_source_changes.json',{'files':changes})
        with self.assertRaisesRegex(ValueError,'exceeds authorized'):guard.check_project(self.root)

    def test_context_choices_reject_rewritten_branding_receipts(self):
        self.choices_upgrade();name=guard.BRANDING_RECORD+'/runtime_manifest.json'
        old=json.loads((self.root/name).read_text());old['rewritten']=True;self.put_json(name,old)
        with self.assertRaisesRegex(ValueError,'prior evidence'):guard.check_project(self.root)

    def mainline_upgrade(self):
        self.choices_upgrade()
        prior=guard.effective_hashes(self.root)
        for name in guard.MAINLINE_HOST_FILES:
            if not (self.root/name).exists():self.put(name,b'prior mainline asset '+name.encode())
        before={'version':'mainline_before_v1','prior_mismatches':[],
            'prior_effective_sha256':prior,'directory_migration':{},
            'files':{p.relative_to(self.root).as_posix():guard.sha(p) for p in self.root.rglob('*') if p.is_file()}}
        self.put_json(guard.MAINLINE_RECORD+'/before_snapshot.json',before)
        changes={}
        for name in guard.MAINLINE_HOST_FILES:
            self.put(name,b'mainline source '+name.encode())
            changes[name]={'before_sha256':before['files'][name],'sha256':guard.sha(self.root/name),'reason':'authorized mainline work'}
        for name in guard.MAINLINE_NEW_FILES:self.put(name,b'pure design readout')
        self.put_json(guard.MAINLINE_RECORD+'/authorized_source_changes.json',{'files':changes})
        self.put_json(guard.MAINLINE_RECORD+'/runtime_manifest.json',{'sha256':{
            name:guard.sha(self.root/name) for name in guard.MAINLINE_HOST_FILES|guard.MAINLINE_NEW_FILES}})
        return changes

    def test_mainline_layer_pins_runtime_without_rewriting_old_receipts(self):
        self.mainline_upgrade()
        self.assertEqual(guard.check_project(self.root)['mainline_runtime_files_checked'],len(guard.MAINLINE_HOST_FILES|guard.MAINLINE_NEW_FILES))
        self.put(next(iter(guard.MAINLINE_NEW_FILES)),b'tampered readout')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_mainline_cannot_change_retained_weight(self):
        self.mainline_upgrade();self.put('saved/policy.json',b'changed weight')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_mainline_cannot_redirect_directory_migration(self):
        self.mainline_upgrade();name=guard.MAINLINE_RECORD+'/before_snapshot.json'
        before=json.loads((self.root/name).read_text())
        before['directory_migration']={'saved/policy.json':'other/policy.json'}
        self.put_json(name,before)
        with self.assertRaisesRegex(ValueError,'migration exceeds'):guard.check_project(self.root)

    def test_mainline_old_evidence_is_immutable(self):
        self.mainline_upgrade();name=guard.CHOICES_RECORD+'/runtime_manifest.json'
        value=json.loads((self.root/name).read_text());value['rewritten']=True;self.put_json(name,value)
        with self.assertRaises(ValueError):guard.check_project(self.root)

    def test_training_directory_move_keeps_weight_bytes_protected(self):
        old='Training_Data_Darcy_CViT/v2/saved_policy.json'
        new='Training_Data/v2/saved_policy.json'
        self.put(old,b'frozen training bytes')
        self.base[old]=guard.sha(self.root/old)
        self.put_json('docs/cleanup/2026-10-28/protected_current.json',{'sha256':self.base})
        self.mainline_upgrade()
        record=guard.MAINLINE_RECORD+'/before_snapshot.json'
        before=json.loads((self.root/record).read_text());before['directory_migration']={old:new}
        self.put_json(record,before)
        (self.root/new).parent.mkdir(parents=True,exist_ok=True)
        (self.root/old).rename(self.root/new)
        self.assertTrue(guard.check_project(self.root)['passed'])
        self.put(new,b'changed training bytes')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def history_upgrade(self):
        self.mainline_upgrade();prior=guard.effective_hashes(self.root)
        for name in guard.SESSION_HISTORY_HOST_FILES:
            if not (self.root/name).exists():self.put(name,b'prior history host')
        before={'version':'session_history_before_v1','prior_effective_sha256':prior,
            'files':{p.relative_to(self.root).as_posix():guard.sha(p) for p in self.root.rglob('*') if p.is_file()}}
        self.put_json(guard.SESSION_HISTORY_RECORD+'/before_snapshot.json',before)
        changes={}
        for name in guard.SESSION_HISTORY_HOST_FILES:
            self.put(name,b'session history host '+name.encode())
            changes[name]={'before_sha256':before['files'][name],'sha256':guard.sha(self.root/name),'reason':'user requested session deletion'}
        for name in guard.SESSION_HISTORY_NEW_FILES:self.put(name,b'app-owned session deletion')
        self.put_json(guard.SESSION_HISTORY_RECORD+'/authorized_source_changes.json',{'files':changes})
        self.put_json(guard.SESSION_HISTORY_RECORD+'/runtime_manifest.json',{'sha256':{
            n:guard.sha(self.root/n) for n in guard.SESSION_HISTORY_HOST_FILES|guard.SESSION_HISTORY_NEW_FILES}})
        return changes

    def test_session_history_source_is_protected(self):
        self.history_upgrade();self.assertEqual(guard.check_project(self.root)['session_history_runtime_files_checked'],6)
        self.put(next(iter(guard.SESSION_HISTORY_NEW_FILES)),b'changed deletion boundary')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_session_deletion_upgrade_cannot_change_retained_weights(self):
        changes=self.history_upgrade();name='saved/policy.json'
        changes[name]={'before_sha256':self.base[name],'sha256':self.base[name],'reason':'out of scope'}
        self.put_json(guard.SESSION_HISTORY_RECORD+'/authorized_source_changes.json',{'files':changes})
        with self.assertRaisesRegex(ValueError,'exceeds authorized'):guard.check_project(self.root)

    def test_session_history_preserves_mainline_receipt(self):
        self.history_upgrade();name=guard.MAINLINE_RECORD+'/runtime_manifest.json'
        value=json.loads((self.root/name).read_text());value['rewritten']=True;self.put_json(name,value)
        with self.assertRaises(ValueError):guard.check_project(self.root)

    def pdf_upgrade(self):
        self.history_upgrade();prior=guard.effective_hashes(self.root)
        before={'version':'pdf_reading_before_v1','prior_effective_sha256':prior,
            'files':{p.relative_to(self.root).as_posix():guard.sha(p) for p in self.root.rglob('*') if p.is_file()}}
        self.put_json(guard.PDF_RECORD+'/before_snapshot.json',before)
        changes={}
        for name in guard.PDF_HOST_FILES:
            self.put(name,b'pdf reading source '+name.encode())
            changes[name]={'before_sha256':prior[name],'sha256':guard.sha(self.root/name),'reason':'user requested PDF meaning extraction'}
        for name in guard.PDF_NEW_FILES:self.put(name,b'bounded PDF artifact '+name.encode())
        self.put_json(guard.PDF_RECORD+'/authorized_source_changes.json',{'files':changes})
        self.put_json(guard.PDF_RECORD+'/runtime_manifest.json',{'sha256':{
            n:guard.sha(self.root/n) for n in guard.PDF_HOST_FILES|guard.PDF_NEW_FILES}})
        return changes

    def test_pdf_worker_and_dependency_are_protected(self):
        self.pdf_upgrade();self.assertEqual(guard.check_project(self.root)['pdf_runtime_files_checked'],13)
        self.put('RUT_Science/rut_science/science_bot/general/planning/pdf_worker.py',b'changed parser')
        with self.assertRaisesRegex(ValueError,'files changed'):guard.check_project(self.root)

    def test_pdf_upgrade_cannot_modify_existing_weights(self):
        changes=self.pdf_upgrade();name='saved/policy.json'
        changes[name]={'before_sha256':self.base[name],'sha256':self.base[name],'reason':'not PDF wiring'}
        self.put_json(guard.PDF_RECORD+'/authorized_source_changes.json',{'files':changes})
        with self.assertRaisesRegex(ValueError,'exceeds authorized'):guard.check_project(self.root)

    def test_pdf_upgrade_keeps_history_receipt_immutable(self):
        self.pdf_upgrade();name=guard.SESSION_HISTORY_RECORD+'/runtime_manifest.json'
        value=json.loads((self.root/name).read_text());value['rewritten']=True;self.put_json(name,value)
        with self.assertRaises(ValueError):guard.check_project(self.root)

    def test_retained_weights_cannot_be_added_to_source_overlay(self):
        changes=self.upgrade()
        changes["saved/policy.json"]={"before_sha256":self.base["saved/policy.json"],"sha256":checksum(b"other"),"reason":"not allowed"}
        self.put_json(guard.PLANNING_RECORD+"/authorized_source_changes.json",{"files":changes})
        with self.assertRaisesRegex(ValueError,"exceeds authorized"):guard.check_project(self.root)

    def test_before_hash_must_match_previous_effective_source(self):
        changes=self.upgrade();name=next(iter(changes));changes[name]["before_sha256"]="0"*64
        self.put_json(guard.PLANNING_RECORD+"/authorized_source_changes.json",{"files":changes})
        with self.assertRaisesRegex(ValueError,"does not chain"):guard.check_project(self.root)

    def test_new_module_tampering_fails(self):
        self.upgrade();self.put(next(iter(guard.PLANNING_NEW_FILES)),b"tampered")
        with self.assertRaisesRegex(ValueError,"files changed"):guard.check_project(self.root)

    def test_provider_transport_cannot_change(self):
        self.upgrade();self.put(next(iter(guard.PROVIDER_FILES)),b"different API")
        with self.assertRaisesRegex(ValueError,"provider/configuration"):guard.check_project(self.root)

    def test_old_manifest_cannot_be_rewritten(self):
        self.upgrade()
        path=guard.TOOL_RECORD+"/runtime_manifest.json"
        self.put_json(path,{"sha256":self.runtime,"rebased":True})
        with self.assertRaisesRegex(ValueError,"Historical baseline"):guard.check_project(self.root)

    def test_runtime_scope_is_explicit(self):
        self.upgrade();path=guard.PLANNING_RECORD+"/runtime_manifest.json"
        value=json.loads((self.root/path).read_text());value["sha256"]["unexpected/new.py"]="0"*64
        self.put_json(path,value)
        with self.assertRaisesRegex(ValueError,"exactly the authorized"):guard.check_project(self.root)

    def test_retained_weights_still_hash_exact(self):
        self.upgrade();self.put("saved/policy.json",b"changed weight")
        with self.assertRaisesRegex(ValueError,"files changed"):guard.check_project(self.root)

    def test_path_traversal_is_not_an_artifact(self):
        with self.assertRaisesRegex(ValueError,"relative artifact"):guard._hashes({"../outside.py":"0"*64})


if __name__=="__main__":unittest.main()
