#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def test_contract_files_exist():
    for rel in ['SKILL.md','adapters/dongyang-annual-v1.yaml','references/calculation-rules.md','scripts/run_pipeline.py','scripts/build_docx.py','scripts/export_review_workbooks.py']:
        assert (ROOT/rel).exists(), rel
def test_adapter_is_json_yaml():
    data=json.loads((ROOT/'adapters/dongyang-annual-v1.yaml').read_text(encoding='utf-8'))
    assert data['sheet']=='25' and data['metrics']['total_flow_m3']['row']==3
def test_feedback_quality_gates():
    model=(ROOT/'scripts/build_analysis_model.py').read_text(encoding='utf-8')
    charts=(ROOT/'scripts/generate_charts.py').read_text(encoding='utf-8')
    draft=(ROOT/'scripts/validate_draft.py').read_text(encoding='utf-8')
    assert 'allow_cross_plant_comparison' in model
    assert "zero_baseline" in charts
    assert 'uncertain_content_in_body' in draft
    assert 'cross_plant_comparison_not_enabled' in draft
    assert (ROOT/'references/reviewer-feedback-rules.md').exists()
def test_cross_platform_workbook_export():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); out=root/'output'; qa=root/'qa'
        model={
            'cost_scope':{'label':'核心生产成本'},'core_cost_total_cny':100,
            'recognized_cost_total_cny':120,'quality_issues':[],
            'monthly_table':{'periods':['2026-01','2026-02'],'rows':[{'label':'日均流量','values':[1,2]}]},
            'removal_table':[],'cost_table':[{'label':'电费','cost_cny':100,'share_pct':100}],
            'resource_table':[],'evidence':[{'evidence_id':'EV-FLOW-ANNUAL','kind':'metric','value':3,'unit':'m3','sources':[]}],
        }
        model_path=root/'model.json'; normalized_path=root/'normalized.json'
        model_path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
        normalized_path.write_text('{}',encoding='utf-8')
        result=subprocess.run([
            sys.executable,str(ROOT/'scripts/export_review_workbooks.py'),
            '--model',str(model_path),'--normalized',str(normalized_path),
            '--output-dir',str(out),'--qa-dir',str(qa),
        ],capture_output=True,text=True,encoding='utf-8',errors='replace')
        assert result.returncode==0,result.stderr
        for name in ['分析结果及图表.xlsx','待确认事项.xlsx','内容追溯表.xlsx']:
            assert (out/name).is_file(),name
        assert (qa/'xlsx-check.json').is_file()
if __name__=='__main__':
    test_contract_files_exist(); test_adapter_is_json_yaml(); test_feedback_quality_gates(); test_cross_platform_workbook_export(); print('smoke-ok')
