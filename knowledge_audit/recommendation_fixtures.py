"""Immutable fictional pilot sources; labels never enter model payloads."""
import csv
import hashlib
import io
import json
from pathlib import Path
from knowledge_audit.privacy import AuditError
from knowledge_audit.inputs import CsvInputAdapter,ColumnMapping
from knowledge_audit.store import BytesInput
from utils.read_only_audit import canonical_sha256,text_sha256

ROOT=Path(__file__).resolve().parents[1]/'fixtures/knowledge_question_recommendations'


def inputs():
    lock=json.loads((ROOT/'lock.json').read_text());body=(ROOT/'inputs.json').read_bytes()
    if hashlib.sha256(body).hexdigest()!=lock['files']['inputs.json']:raise AuditError('recommendation_fixture_drift')
    return json.loads(body),lock


def snapshot(spec):
    records=[]
    for s in spec['records']:
        content='question: '+s['question']+'\nanswer: '+s['answer']
        records.append({'chunk_id':s['id'],'faq_entry_id':s['id'],'question':s['question'],'answer':s['answer'],'content':content,
            'content_sha256':text_sha256(content),'source_content_sha256':text_sha256(content),
            'document_title':'Synthetic_FableBank','document_id':'synthetic-a4','document_revision':1,'chunk_index':len(records),
            'main_category':s['category'],'sub_category':s['subcategory'],'taxonomy_status':'structured','redaction_changed':False})
    value={'schema_version':'a1-kb-snapshot-1','source_signature':{'kind':'controlled_static_fictional_fixture'},'retrieval_frozen':True,'records':records}
    value['snapshot_id']=canonical_sha256(value)
    return value


def dataset(spec,redactor):
    body=io.StringIO(newline='');writer=csv.writer(body);writer.writerow(['query'])
    for case in spec['cases']:writer.writerow([case['query']])
    return CsvInputAdapter(BytesInput(body.getvalue().encode('utf-8-sig')),ColumnMapping('query')).load(redactor)


class A4DispatchBudget:
    """A4-wide hard ceiling. Caller must hold CoverageStore.global_lease."""
    def __init__(self,store,directory):
        from knowledge_audit.privacy import private_json
        self.store=store;self.path=directory/'a4-budget.json'
        if not self.path.exists():private_json(self.path,{'version':'a4-dispatch-budget-1','limit':40,'used':0,'blocked':0})
        self.state=store.read(self.path)
        if self.state['limit']!=40 or type(self.state['used']) is not int or not 0<=self.state['used']<=40:raise AuditError('invalid_a4_budget')
    def reserve(self):
        if self.state['used']>=40:
            self.state['blocked']+=1;self.store.write(self.path,self.state);raise AuditError('diagnostic_budget_exhausted')
        self.state['used']+=1;self.store.write(self.path,self.state)
