from statistics import median, quantiles
import json
from ..agent import build_agent
from ..registry import ToolRegistry


QUERIES=[
 '番茄在高盐条件下可能出现哪些生长影响？','高盐条件下应该把灌水量提高多少？','苗期如何控制水分？',
 '番茄缺氮有什么表现？','番茄缺钾有什么表现？','根区EC升高怎么办？','基质含水率过低有什么风险？',
 '开花坐果期如何管理水肥？','果实膨大期怎样施肥？','番茄萎蔫可能是什么原因？','温室高温对番茄有什么影响？',
 '低温会影响番茄坐果吗？','湿度过高有什么病害风险？','CO2不足会影响生长吗？','光照不足有什么影响？',
 '灌溉频率如何判断？','排液率能说明什么？','pH过高有什么影响？','钙不足为什么会脐腐？','镁缺乏有什么症状？',
 '氮肥过量有什么风险？','盐胁迫如何缓解？','定植缓苗期注意什么？','成熟采收期水肥怎么管理？','今天股票涨了吗？']


def run_rag_analysis(destination):
    registry=ToolRegistry(); rows=[]; scores=[]
    for query in QUERIES:
        result=registry.call('retrieve_water_fertilizer_knowledge',{'query':query,'top_k':6})
        values=[e.score for e in result.evidence if e.score is not None]; scores.extend(values)
        rows.append({'query':query,'scores':values,'evidence_ids':[e.evidence_id for e in result.evidence]})
    salinity={}
    for profile in ('baseline','improved'):
        run=build_agent(profile=profile).ask(QUERIES[0],debug=True)
        salinity[profile]={'accepted_ids':run.state.knowledge_evidence_ids,
            'sufficiency':run.answer.evidence_sufficiency.value,'gate':run.debug['relevance_gate']}
    quartiles=quantiles(scores,n=4)
    payload={'n_queries':len(QUERIES),'n_scores':len(scores),'score_distribution':{
        'min':min(scores),'q1':quartiles[0],'median':median(scores),'q3':quartiles[2],'max':max(scores)},
        'selected_minimum_score':3.0,
        'threshold_reason':'The unrelated stock-market query has top score 2; valid and invalid queries overlap, so score 3 is only Layer 1 and cannot replace semantic relevance judgment.',
        'queries':rows,'salinity_before_after':salinity}
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload
