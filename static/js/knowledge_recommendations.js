/* A4 question/taxonomy proposals. Text-only rendering; no private browser storage. */
(function (global) {
    'use strict';
    const labels = {
        retrieval_improvement_not_kb_gap:'The answer is covered. Improve retrieval rather than draft a KB question.',
        knowledge_already_covered:'The knowledge already covers this question.',
        conflicting_full_coverage_observation:'Another comparable run found full coverage. Review the disagreement first.',
        missing_aspects_not_identified:'No validated missing information has been identified.',
        coverage_not_completed:'Coverage preparation or evaluation is not complete.',
        preparation_not_resolved:'The intended question still needs context or preparation review.',
        unresolved_evaluation_issue:'Evaluation or compatibility issues require review.',
        context_or_compatibility_unresolved:'Context or compatible conditions remain unresolved.',
        verification_unresolved:'Coverage verification needs review.',
        incompatible_snapshot_or_run:'The knowledge or run revision is incompatible.',
        coverage_error:'A failed evaluation cannot establish missing knowledge.',
        coverage_pending:'This question has not been evaluated.',coverage_needs_context:'Preceding context is missing.',
        coverage_needs_review:'The evaluation needs review.',coverage_excluded:'This question is excluded from KB auditing.'
    };
    const display = value => labels[value] || String(value || 'Unavailable').replaceAll('_',' ');
    function mount(container,identity) {
        const document=container.ownerDocument, workspace=document.getElementById('coverageRoot');
        const root=document.createElement('section');root.className='coverage-recommendations';root.setAttribute('aria-label','Knowledge-team question recommendations');root.tabIndex=-1;container.append(root);
        let revision='',timer=null,stopped=false,requestSequence=0;let current=null,revisionPicker=null;
        function el(tag,text,className) {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
        function paragraph(text) {const n=el('p',text);n.dir='auto';return n;}
        async function api(path,options) {const response=await global.fetch('/api/knowledge-coverage/'+path,options);const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Recommendation operation could not complete.');return body;}
        function post(path,value) {return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value || {})});}
        function button(title,fn,className) {const n=el('button',title,className||'coverage-secondary');n.type='button';n.addEventListener('click',async()=>{if(stopped||!root.isConnected)return;n.disabled=true;try{await fn();}catch(error){message(error.message,true);}finally{n.disabled=false;if(!n.isConnected&&root.isConnected)root.focus();}});return n;}
        function message(text,error) {if(stopped||!root.isConnected)return;let status=root.querySelector('.recommendation-status');if(!status){status=el('p',undefined,'recommendation-status');status.setAttribute('aria-live','polite');root.append(status);}status.textContent=text;status.setAttribute('role',error?'alert':'status');}
        function clearTimer() {if(timer){global.clearInterval(timer);timer=null;}}
        function stop(){stopped=true;requestSequence++;clearTimer();if(observer)observer.disconnect();}
        const observer=global.MutationObserver?new global.MutationObserver(()=>{if(!root.isConnected)stop();}):null;
        if(observer)observer.observe(document.body,{childList:true,subtree:true});
        function base() {root.replaceChildren(el('h3','Questions for the knowledge team'));root.append(paragraph('Automatic drafts are proposals. Independent confirmation of the gap and factual answers remains pending. Review approval never writes to the knowledge base.'));}
        function reasons(value) {const items=el('ul',undefined,'recommendation-reasons');(value.reason_codes||[]).forEach(code=>items.append(el('li',display(code))));root.append(items);}
        async function availability() {
            if(stopped||!root.isConnected)return;const sequence=++requestSequence;
            const value=await api('runs/'+encodeURIComponent(identity.runId)+'/rows/'+encodeURIComponent(identity.rowId)+'/recommendations');
            if(stopped||!root.isConnected||sequence!==requestSequence)return;
            base();reasons(value.eligibility);
            if(value.revisions.length){
                const label=el('label','Viewing draft revision');const choose=el('select');
                value.revisions.forEach(info=>{const option=el('option',info.created_at+' · '+info.state+' · '+info.recommendation_revision_id.slice(-8));option.value=info.recommendation_revision_id;choose.append(option);});
                revision=revision||value.revisions[0].recommendation_revision_id;choose.value=revision;
                choose.addEventListener('change',()=>{revision=choose.value;load().catch(error=>message(error.message,true));});label.append(choose);revisionPicker=label;root.append(label);await load();return;
            }
            if(value.operational_limits)root.append(paragraph('Draft limit: '+value.operational_limits.completion_attempts+' completion attempts; '+value.operational_limits.token_allowance+' reserved/used tokens; '+value.operational_limits.execution_seconds+' execution seconds. Unknown usage remains charged.'));
            if(value.eligibility.eligible){message('Eligible for a possible-gap draft. Human gap confirmation is still pending.');
                if(workspace.dataset.canStart==='true' && workspace.dataset.canExport==='true')root.append(button('Draft questions for review',create,'coverage-primary'));
                else root.append(paragraph('Your account can view findings. Drafting requires explicit pilot and export access.'));
            } else message('Recommendations are unavailable for this coverage result.');
        }
        async function create() {
            message('Pinning the coverage result and preparing a question-only draft…');
            const source=identity.getCoverageSource?identity.getCoverageSource():'';
            if(!source){if(identity.focusCoverageSource)identity.focusCoverageSource();throw new Error('Select or freeze a coverage source in Run download first. This draft will use that same source.');}
            const data=await post('runs/'+encodeURIComponent(identity.runId)+'/recommendations',{coverage_export_revision_id:source,row_ids:[identity.rowId]});
            if(stopped||!root.isConnected)return;revision=data.recommendation_revision_id;if(identity.onRevisionChange)await identity.onRevisionChange();await load();
        }
        async function load() {
            if(stopped||!root.isConnected){stop();return;}const sequence=++requestSequence,requested=revision;
            const value=await api('recommendations/'+encodeURIComponent(requested));if(stopped||!root.isConnected){stop();return;}if(sequence!==requestSequence||requested!==revision)return;
            current=value;base();if(revisionPicker)root.append(revisionPicker);const result=value.results[identity.rowId];reasons(result.eligibility);
            const info=value.revision;message(display(info.state)+' · '+display(info.phase));
            const allowance=value.operational_budget||{};
            if(allowance.version)root.append(paragraph('Draft allowance: '+allowance.completion_attempts+' completion attempts used; '+allowance.remaining_completions+' remaining; '+allowance.tokens_charged+' tokens charged/reserved. '+(info.pause_reason||'')+'. A new draft revision has its own explicit allowance; prior usage stays recorded.'));

            if(['queued','running'].includes(info.state)){
                root.append(paragraph('Preparing structured missing-information findings, then question and taxonomy proposals.'));
                if(workspace.dataset.canStart==='true')root.append(button('Cancel question drafting',async()=>{await post('recommendations/'+revision+'/cancel');await load();}));
                if(!timer)timer=global.setInterval(()=>load().catch(error=>{clearTimer();message(error.message,true);}),1000);
            }else{clearTimer();if(identity.onRevisionChange)identity.onRevisionChange().catch(error=>message(error.message,true));
                if((result.review_unavailable_reasons||[]).length)root.append(paragraph('The title-matching policy changed after this saved draft. Create a new revision before approval; coverage results are unchanged.'));
                if(result.error_code)root.append(paragraph('Drafting unavailable: '+display(result.error_code)+'. The coverage verdict has not changed.'));
                if(result.recommendation_status==='interrupted')root.append(paragraph('Question drafting was interrupted. No recommendation has been fabricated.'));
            }
            (result.gap_specifications||[]).forEach(gap=>{const block=el('div',undefined,'recommendation-gap');block.append(el('strong','Missing information · '+gap.missing_aspect_ids.join(', ')),paragraph(gap.missing_information));
                if(gap.conditions.length)block.append(paragraph('Conditions: '+gap.conditions.join(' · ')));
                root.append(block);});
            (result.recommendations||[]).forEach(item=>{
                const card=el('article',undefined,'recommendation-card');card.setAttribute('data-recommendation-id',item.recommendation_id);
                card.append(el('strong',display(item.action),'recommendation-action'),paragraph(item.recommended_question));
                const path=el('p',item.category+' / '+(item.subcategory||'No subcategory'),'recommendation-taxonomy');path.dir='auto';card.append(path);
                card.append(el('span',display(item.taxonomy_status)+' · human review required','coverage-badge'));
                card.append(paragraph(item.justification),paragraph('Uncertainty: '+item.uncertainty.join(' · ')));
                const related=Array.from(new Set([...(item.related_faq_ids||[]),...(item.equivalent_faq_ids||[])]));
                related.forEach(id=>{const link=el('a','Snapshot FAQ '+id,'coverage-link');link.href='/api/knowledge-coverage/recommendations/'+encodeURIComponent(revision)+'/metadata/'+encodeURIComponent(id);link.target='_blank';link.rel='noopener';card.append(link);});
                const decision=value.review.decisions[identity.rowId+':'+item.recommendation_id] || {status:'unreviewed'};
                card.append(el('p','Recommendation review: '+display(decision.status),'recommendation-review-state'));
                if(workspace.dataset.canReview==='true' && info.state==='completed'){
                    const noteLabel=el('label','Review note · optional');const note=el('textarea');note.maxLength=600;note.rows=2;note.dir='auto';noteLabel.append(note);card.append(noteLabel);
                    const controls=el('div',undefined,'recommendation-review-controls');
                    [['Approve question proposal','approved'],['Request changes','needs_changes'],['Reject proposal','rejected']].forEach(([title,state])=>{
                        const control=button(title,async()=>{await post('recommendations/'+revision+'/reviews',{source_row_id:identity.rowId,recommendation_id:item.recommendation_id,decision:state,note:note.value});if(stopped||!root.isConnected)return;await load();});
                        if(state==='approved' && (!result.eligibility.eligible || result.approval_allowed===false))control.disabled=true;controls.append(control);
                    });
                    card.append(controls);
                }else if(workspace.dataset.canReview!=='true')card.append(paragraph('Review controls require an explicit recommendation-review grant.'));
                root.append(card);
            });
            if(workspace.dataset.canExport==='true')root.append(button('Prepare CSV for this draft revision only',async()=>{
                const exported=await post('recommendations/'+revision+'/export-revisions',{review_revision_id:value.review.review_revision_id||null});
                const wrap=el('div',undefined,'recommendation-downloads');
                [['CSV with all rows','export'],['Matching manifest','export-manifest']].forEach(([title,route])=>{const link=el('a',title,'coverage-link');link.href='/api/knowledge-coverage/recommendations/'+encodeURIComponent(revision)+'/'+route+'?export_revision_id='+encodeURIComponent(exported.export_revision_id);link.setAttribute('download','');wrap.append(link);});
                wrap.append(paragraph(exported.row_count+' rows · coverage '+display(info.state)+' · pinned review '+(exported.review_revision_id||'unreviewed')+'. Prepare a new download to include later review decisions.'));wrap.append(paragraph('This revision-specific download does not include other drafts. Use Run download to select revisions across rows.'));root.append(wrap);
            }));
            if(result.eligibility.eligible && !['queued','running'].includes(info.state) && workspace.dataset.canStart==='true' && workspace.dataset.canExport==='true')root.append(button('Create new draft revision',create));
            const details=el('details');details.append(el('summary','Recommendation provenance'));
            details.append(paragraph('Coverage export '+info.source_export_id),paragraph('Recommendation revision '+revision),paragraph('Snapshot '+info.snapshot_id),paragraph('Rubric '+info.versions.prompts.rubric_version),paragraph('Independent gap confirmation: not reviewed. Real-query calibration: pending.'));
            if(result.title_lookup)details.append(paragraph('Title lookup: '+result.title_lookup.selected_count+' of '+result.title_lookup.candidate_count+' candidates; '+result.title_lookup.metadata_records_examined+' metadata entries examined. Titles do not prove coverage.'));
            root.append(details);
        }
        base();message('Checking recommendation eligibility…');availability().catch(error=>message(error.message,true));
        return {refresh:load,stop};
    }
    global.KnowledgeRecommendations={mount};
    if(typeof module!=='undefined'&&module.exports)module.exports={mount};
})(typeof window!=='undefined'?window:globalThis);
