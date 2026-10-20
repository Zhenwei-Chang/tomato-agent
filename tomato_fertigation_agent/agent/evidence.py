from ..schemas.agent import AggregatedEvidence, EvidenceSufficiency, FactItem, PredictionItem, HistoricalCaseEvidence
from ..schemas.common import Confidence


def _unique(values):
    return list(dict.fromkeys(v for v in values if v))


class EvidenceAggregator:
    UNITS={'plant_height_cm':'cm','lai':None,'stem_diameter_mm':'mm','growth_state':None}

    def aggregate(self, results, accepted_knowledge, sufficiency, state,
                  evidence_registry=None, ids_by_tool_call=None, reliability_ids=None):
        evidence_registry=list(evidence_registry or [])
        ids_by_tool_call=ids_by_tool_call or {}
        facts=[]; predictions=[]; historical=[]; historical_evidence=[]; case_prediction=None; warnings=list(state.warnings); limitations=[]; confidences=[]
        for result in results:
            name=result.metadata.tool_name
            ids=ids_by_tool_call.get(result.metadata.tool_call_id,
                                     [e.evidence_id for e in result.evidence])
            warnings.extend(result.warnings); limitations.extend(result.metadata.limitations)
            confidences.append(result.metadata.confidence)
            if result.status=='error':
                warnings.append(f'{name} failed: {result.error.code.value}'); continue
            data=result.data; scope=result.metadata.scope
            if name=='get_growth_context':
                for key,value in data.get('phenotype',{}).items():
                    if value is not None: facts.append(FactItem(name=key,value=value,unit=self.UNITS.get(key),scope=scope,source_tool=name,evidence_ids=ids,observed=True))
                if data.get('environment',{}).get('values'):
                    facts.append(FactItem(name='environment_snapshot',value=data['environment']['values'],scope='greenhouse',source_tool=name,evidence_ids=ids,observed=True))
            elif name=='get_sensor_history':
                facts.append(FactItem(name='sensor_history_summary',value=data.get('summary',{}),scope='greenhouse',source_tool=name,evidence_ids=ids,observed=True))
            elif name=='get_treatment_recipe':
                facts.append(FactItem(name='treatment_recipe',value={'treatment_id':data['treatment_id'],'fertilizer_salts':data['fertilizer_salts'],'elements':data['elements']},scope='treatment',source_tool=name,evidence_ids=ids,observed=True))
            elif name=='predict_height_t7':
                p=data['prediction']; predictions.append(PredictionItem(name='height_t7',value=p['height_t7_cm'],unit='cm',scope=scope,horizon_days=7,source_tool=name,model_version=result.metadata.model_version,evidence_ids=ids))
                for key,unit in [('height_t0_cm','cm'),('lai_t0',None)]:
                    facts.append(FactItem(name=key.replace('_t0_cm','_cm').replace('_t0',''),value=data['current_state'][key],unit=unit,scope='plant',source_tool=name,evidence_ids=ids,observed=True))
            elif name=='analyze_rgb':
                p=data['prediction']; predictions.extend([
                    PredictionItem(name='current_view_mean_height',value=p['current_view_mean_height_cm'],unit='cm',scope='view',source_tool=name,model_version=result.metadata.model_version,evidence_ids=ids),
                    PredictionItem(name='future_view_mean_height_t7',value=p['future_view_mean_height_t7_cm'],unit='cm',scope='view',horizon_days=7,source_tool=name,model_version=result.metadata.model_version,evidence_ids=ids)])
            elif name=='find_similar_cases':
                historical_evidence.extend(
                    item for item in evidence_registry if item.evidence_id in ids)
                for match in data.get('matches',[]):
                    historical.append(HistoricalCaseEvidence(case_id=match['case_id'],scope=match['scope'],similarity=match['similarity'],
                        case_date=match['case_date'],outcome_date=match['outcome_date'],historical_outcome=match['historical_outcome'],
                        domain_warning=match.get('domain_warning',False),
                        evidence_id=(next((eid for eid in ids if eid == match['case_id']),
                                          match['case_id'])),
                        query_timestamp=(data.get('query_case') or {}).get('date'),
                        retrieval_mode=data.get('retrieval_mode'),
                        retrieval_confidence=data.get('retrieval_confidence','UNKNOWN'),
                        source_tool_call_id=result.metadata.tool_call_id))
                case_prediction=data.get('summary',{}).get('similarity_weighted_height_t7_cm')
        if not confidences: overall=Confidence.UNKNOWN
        else:
            rank={Confidence.LOW:0,Confidence.UNKNOWN:1,Confidence.MEDIUM:2,Confidence.HIGH:3}
            overall=min(confidences,key=lambda x:rank[x])
        if sufficiency==EvidenceSufficiency.INSUFFICIENT and overall!=Confidence.LOW: overall=Confidence.LOW
        model_prediction=next((p.value for p in predictions if p.name=='height_t7'),None)
        agreement='NOT_AVAILABLE'
        if model_prediction is not None and case_prediction is not None:
            difference=abs(model_prediction-case_prediction)
            agreement='AGREE' if difference<=10 else ('PARTIAL' if difference<=20 else 'DISAGREE')
            if agreement=='DISAGREE': warnings.append(f'ML prediction and Case-weighted prediction disagree by {difference:.2f} cm.')
        return AggregatedEvidence(facts=facts,predictions=predictions,knowledge_evidence=accepted_knowledge,
            historical_case_evidence=historical_evidence,
            evidence_registry=evidence_registry,
            reliability_evidence_ids=list(reliability_ids or []),
            historical_cases=historical,case_prediction_height_t7_cm=case_prediction,case_model_agreement=agreement,
            warnings=_unique(warnings),limitations=_unique(limitations),unsupported_requests=_unique(state.unsupported_requests),
            evidence_sufficiency=sufficiency,confidence=overall)
