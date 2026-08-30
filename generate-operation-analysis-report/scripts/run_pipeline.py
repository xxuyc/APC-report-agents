#!/usr/bin/env python3
import argparse, json, shutil, subprocess, sys
from pathlib import Path
from common import timestamp, read_json, sha256, write_json

ROOT=Path(__file__).resolve().parents[1]
REPO_ROOT=ROOT.parent
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from knowledge_center.pipeline import normalize_knowledge_mode, prepare_snapshot
from knowledge_center.evidence import register_operation_references
from knowledge_center.writeback import writeback_operation_artifacts
from knowledge_center.core import KnowledgeUnavailable, ProjectConfirmationRequired, repository_from_options, resolve_project
def run(cmd):
    result=subprocess.run([str(x) for x in cmd],check=False)
    if result.returncode: raise SystemExit(result.returncode)
def manifest_path(run_dir): return run_dir/'manifest.json'
def prepare(a):
    knowledge_mode=normalize_knowledge_mode(a.knowledge_mode,a.disable_knowledge)
    if not a.project_id:
        if knowledge_mode=='disabled':
            print(json.dumps({'status':'input_error','message':'本地模式请提供 --project-id；启用知识中心后可由项目路由器识别。'},ensure_ascii=False)); raise SystemExit(2)
        try:
            repository=repository_from_options(a.knowledge_store,allow_empty=False); resolved=resolve_project(repository,explicit_project_name=a.project_name,input_paths=[a.input]); a.project_id=resolved['project_id']; a.project_name=a.project_name or resolved.get('project_name') or a.project_id
        except (KnowledgeUnavailable,ProjectConfirmationRequired) as exc:
            print(json.dumps(exc.as_dict(),ensure_ascii=False)); raise SystemExit(6)
    workspace=Path(a.workspace).resolve(); run_dir=workspace/'projects'/a.project_id/'runs'/a.run_id
    for p in ['input','working','charts','output','qa']: (run_dir/p).mkdir(parents=True,exist_ok=True)
    source=Path(a.input).resolve(); snap=run_dir/'input'/source.name; shutil.copy2(source,snap)
    profile=Path(a.profile).resolve(); adapter=Path(a.adapter).resolve(); py=sys.executable; w=run_dir/'working'
    source_cmd=[py,ROOT/'scripts/build_source_index.py','--input',snap,'--adapter',adapter,'--profile',profile,'--output',w/'source-index.json']
    if a.reference: source_cmd += ['--reference',Path(a.reference).resolve()]
    run(source_cmd)
    run([py,ROOT/'scripts/inspect_workbook.py',snap,w/'workbook-inspection.json'])
    run([py,ROOT/'scripts/normalize_data.py','--input',snap,'--adapter',adapter,'--profile',profile,'--output',w/'normalized-data.json'])
    cmd=[py,ROOT/'scripts/validate_data.py','--data',w/'normalized-data.json','--inspection',w/'workbook-inspection.json','--profile',profile,'--output',w/'validation.json']
    if a.golden_profile: cmd += ['--golden-profile',Path(a.golden_profile).resolve()]
    run(cmd); run([py,ROOT/'scripts/compute_metrics.py','--data',w/'normalized-data.json','--profile',profile,'--validation',w/'validation.json','--output',w/'metrics.json'])
    run([py,ROOT/'scripts/build_analysis_model.py','--data',w/'normalized-data.json','--metrics',w/'metrics.json','--profile',profile,'--output',w/'analysis-model.json','--chart-spec',w/'chart-spec.json'])
    run([py,ROOT/'scripts/generate_charts.py','--spec',w/'chart-spec.json','--output-dir',run_dir/'charts'])
    knowledge_path=w/'knowledge-snapshot.json'
    knowledge=prepare_snapshot(output=knowledge_path,project_id=a.project_id,project_name=a.project_name or a.project_id,agent_type='generate-operation-analysis-report',input_paths=[snap],store_path=a.knowledge_store,query=a.retrieval_query,intents=a.knowledge_intent or [],reference_ids=a.reference_project_id or [],mode=knowledge_mode)
    register_operation_references(w/'analysis-model.json',knowledge)
    model=read_json(w/'analysis-model.json'); request=['# Agent 写作任务','仅依据 analysis-model.json 撰写 drafted-content.json；不得自行计算，不得宣称稳定达标或因果关系。','普通正文只写已确认事实；关键输入写入 callouts（kind=critical_input），其他质量问题仅进入待确认工作簿。','默认不做厂际比较；建设需求只能采用 suggested_requirements 中已批准的系统方向。',f"开篇来源句：{model.get('data_provenance_opening') or '根据项目方提供的生产运营数据……'}",'', '可使用的建议结论：']+[f"- {x['claim_id']}：{x['text']}" for x in model['suggested_claims']+model['suggested_requirements']]
    request += ['', f'Cross-project knowledge snapshot: {knowledge_path}', 'Historical writing and methods are references only. Current-project metrics must come from deterministic analysis-model.json. Historical numbers may only come from benchmark_data with project, period, unit, and formula version retained.']
    (w/'agent-request.md').write_text('\n'.join(request),encoding='utf-8')
    plan=knowledge['retrieval_plan']
    write_json(manifest_path(run_dir),{'project_id':a.project_id,'project':a.project_name or a.project_id,'run_id':a.run_id,'agent_type':'generate-operation-analysis-report','status':'ready_to_draft','created_at':timestamp(),'input':str(snap),'input_sha256':sha256(snap),'skill_version':'0.1.0','outputs':[],'knowledge_mode':knowledge_mode,'knowledge_status':plan['knowledge_status'],'knowledge_warning':plan.get('warning'),'knowledge_store':str(Path(a.knowledge_store).resolve()) if a.knowledge_store else '', 'knowledge_snapshot':str(knowledge_path),'knowledge_snapshot_sha256':knowledge['sha256'],'retrieval_intents':plan['intents'],'reference_project_ids':plan['reference_project_ids']})
    print(run_dir)
def finalize(a):
    run_dir=Path(a.run_dir).resolve(); w=run_dir/'working'; out=run_dir/'output'; qa=run_dir/'qa'; out.mkdir(exist_ok=True); qa.mkdir(exist_ok=True); py=sys.executable
    run([py,ROOT/'scripts/validate_draft.py','--draft',w/'drafted-content.json','--model',w/'analysis-model.json','--output',qa/'draft-validation.json'])
    run([py,ROOT/'scripts/build_docx.py','--model',w/'analysis-model.json','--draft',w/'drafted-content.json','--charts',run_dir/'charts','--standalone',out/'生产运营数据分析报告.docx','--chapter',out/'方案章节_运营数据现状评估.docx'])
    run([py,ROOT/'scripts/export_review_workbooks.py','--model',w/'analysis-model.json','--normalized',w/'normalized-data.json','--output-dir',out,'--qa-dir',qa/'xlsx-check'])
    m=read_json(manifest_path(run_dir)); issues=read_json(w/'validation.json')['issues']; m.update({'status':'completed_with_warnings' if issues else 'completed','completed_at':timestamp(),'warnings':len([x for x in issues if x['severity']=='warning']),'outputs':[p.name for p in out.iterdir() if p.suffix.lower() in {'.docx','.xlsx'}]}); write_json(manifest_path(run_dir),m); print(json.dumps(m,ensure_ascii=False,indent=2))
def record_qa(a):
    run_dir=Path(a.run_dir).resolve(); m=read_json(manifest_path(run_dir)); m['qa']={'docx_visual':a.docx_visual,'xlsx_visual':a.xlsx_visual,'formula_errors':int(a.formula_errors),'recorded_at':timestamp()}
    if a.docx_visual=='passed' and a.xlsx_visual=='passed' and int(a.formula_errors)==0:
        m['status']='completed' if not m.get('warnings') else 'completed_with_warnings'
        if m.get('knowledge_status')=='enabled':
            try:
                writeback_operation_artifacts(m,run_dir,m.get('knowledge_store') or None); m['knowledge_writeback']='completed'
            except KnowledgeUnavailable as exc:
                m['knowledge_writeback']='failed'; m['knowledge_warning']=str(exc)
                if m.get('knowledge_mode')=='required':
                    write_json(manifest_path(run_dir),m); print(json.dumps({'status':'knowledge_unavailable','message':str(exc)},ensure_ascii=False)); raise SystemExit(7)
    else: m['status']='qa_failed'
    write_json(manifest_path(run_dir),m); print(json.dumps(m['qa'],ensure_ascii=False,indent=2))
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('prepare'); q.add_argument('--workspace',required=True); q.add_argument('--project-id'); q.add_argument('--project-name'); q.add_argument('--run-id',required=True); q.add_argument('--input',required=True); q.add_argument('--adapter',required=True); q.add_argument('--profile',required=True); q.add_argument('--golden-profile'); q.add_argument('--reference'); q.add_argument('--knowledge-store'); q.add_argument('--retrieval-query'); q.add_argument('--knowledge-intent',action='append'); q.add_argument('--reference-project-id',action='append'); q.add_argument('--knowledge-mode',choices=['disabled','optional','required'],default='disabled'); q.add_argument('--disable-knowledge',action='store_true')
    q=sub.add_parser('finalize'); q.add_argument('--run-dir',required=True)
    q=sub.add_parser('status'); q.add_argument('--run-dir',required=True)
    q=sub.add_parser('record-qa'); q.add_argument('--run-dir',required=True); q.add_argument('--docx-visual',choices=['passed','failed'],required=True); q.add_argument('--xlsx-visual',choices=['passed','failed'],required=True); q.add_argument('--formula-errors',default='0')
    a=p.parse_args()
    if a.command=='prepare': prepare(a)
    elif a.command=='finalize': finalize(a)
    elif a.command=='record-qa': record_qa(a)
    else: print(json.dumps(read_json(manifest_path(Path(a.run_dir))),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
