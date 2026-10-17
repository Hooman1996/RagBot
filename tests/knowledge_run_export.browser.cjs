/* A5 actual Chromium; synthetic auth/checkpoints only, no inference services. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const local=require('node:module').createRequire(path.resolve(process.argv[2],'package.json'));
const {chromium:engine}=local('playwright'),mod=local('@sparticuz/chromium'),chromium=mod.default||mod;
const origin=process.argv[3],output=path.resolve(process.argv[4]);assert.equal(new URL(origin).hostname,'127.0.0.1');fs.mkdirSync(output,{recursive:true,mode:0o700});
let step='start';const checks=[],screenshots=[];
async function run(){
 chromium.setGraphicsMode=false;
 const browser=await engine.launch({executablePath:await chromium.executablePath(),args:[...chromium.args,'--disable-gpu'],headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true,reducedMotion:'reduce'}),page=await context.newPage();
 const requests=[],safePageErrors=[];let pageErrors=0;page.on('pageerror',error=>{pageErrors++;safePageErrors.push({category:error.name,sites:Array.from(error.stack.matchAll(/(knowledge_[a-z_]+\.js):(\d+):(\d+)/g),m=>({file:m[1],line:Number(m[2]),column:Number(m[3])}))});});page.on('request',r=>requests.push(new URL(r.url()).pathname));
 await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 async function shot(name){await page.screenshot({path:path.join(output,name)});screenshots.push(name);}
 async function openRow(button){await button.click();await page.locator('#coverage-detail-proposals summary').click();}
 async function cards(){await page.locator('.recommendation-card').nth(1).waitFor({timeout:20000});}
 async function review(index,name,state){await page.locator('.recommendation-card').nth(index).getByRole('button',{name,exact:true}).click();await page.waitForFunction(({index,state})=>document.querySelectorAll('.recommendation-review-state')[index]?.textContent.includes(state),{index,state});}
 try{
  step='upload';assert.equal((await context.request.post(origin+'/api/login',{data:{username:'planner-synthetic',password:'synthetic-browser-only'}})).status(),200);
  await page.goto(origin+'/knowledge-coverage');await page.locator('#coverageRoot').waitFor();await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.classList.contains('coverage-skip')),true);
  const questions=Array(918).fill('پرسش آزمایشی با نیم‌فاصله، "نقل قول"\nخط دوم؟');
  questions[0]='Synthetic partial duration and cutoff? پرسش طولانی آزمایشی، '+('درخواست کارت و شرایط ارسال، '.repeat(9))+'\nخط دوم';
  questions[1]='Synthetic partial alternative duration and cutoff? پرسش دوم';questions[2]='Synthetic approval duration and cutoff?';questions[3]='Synthetic invalid citation duration and cutoff?';questions[4]='Synthetic full approval duration and cutoff?';questions[7]='';questions[917]=questions[0];
  const csv='\ufeffquery\r\n'+questions.map(q=>'"'+q.replaceAll('"','""')+'"').join('\r\n')+'\r\n';
  await page.locator('#coverageFile').setInputFiles({name:'synthetic-a5-918.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
  step='upload_headers';await page.waitForFunction(()=>document.getElementById('coverageQueryColumn').value==='query');await page.locator('#coverageUpload').click();
  step='upload_preparation';await page.waitForFunction(()=>document.querySelectorAll('#coverageRows input[type=checkbox]').length===25);
  await page.locator('#coverageSnapshot').selectOption({label:await page.locator('#coverageSnapshot option').filter({hasText:'2 entries'}).textContent()});
  for(let i=0;i<5;i++)await page.locator('#coverageRows input[type=checkbox]').nth(i).check();
  step='pilot_run';await page.locator('#coverageStart').click();await page.waitForFunction(()=>document.getElementById('coverageProgressText').textContent.startsWith('completed'),{},{timeout:30000});
  assert.match(await page.locator('#coverageProgressText').textContent(),/5 of 5.*918 rows retained/);
  assert.match(await page.locator('#coverageRunCounts').textContent(),/918/);assert.match(await page.locator('#coverageDatasetSummary').textContent(),/918/);
  checks.push('authenticated_upload_mapping_918_rows_five_pilot_progress_and_preparation_denominators');
  const run=await page.locator('#coverageRuns').inputValue();const base='/api/knowledge-coverage/runs/'+run;
  step='shared_source';await page.locator('#coverageFreezeSource').click();await page.waitForFunction(()=>!!document.getElementById('coverageExportSource').value);const source=await page.locator('#coverageExportSource').inputValue();
  await page.locator('#coverageFilter').selectOption('possible_partial_gap');await page.waitForFunction(()=>document.querySelectorAll('#coverageRows button').length===2);
  const rowIds=await page.locator('#coverageRows button').evaluateAll(bs=>bs.map(b=>b.id.replace('coverage-review-','')));
  step='draft_review';await openRow(page.locator('#coverageRows button').first());await page.getByRole('button',{name:'Draft questions for review',exact:true}).click();await cards();
  const approve=page.locator('.recommendation-card').first().getByRole('button',{name:'Approve question proposal',exact:true});await approve.focus();await page.keyboard.press('Enter');
  await page.waitForFunction(()=>document.querySelector('.recommendation-review-state')?.textContent.includes('approved'));assert.equal(await page.evaluate(()=>document.activeElement.classList.contains('coverage-recommendations')),true);
  assert.match(await page.locator('.recommendation-card').nth(1).textContent(),/unreviewed/);
  const faq=page.locator('.recommendation-card a').first();assert.equal((await context.request.get(origin+await faq.getAttribute('href'))).status(),200);
  // The aspect source link must open its collapsed evidence group before navigation.
  const evidenceLink=page.locator('#coverage-detail-aspects a').first();await evidenceLink.click();assert.equal(await page.locator('#coverage-detail-sources').getAttribute('open'),'');
  const anchor=await evidenceLink.getAttribute('href');await page.locator(anchor).waitFor({state:'visible'});
  await page.locator('#coverageCloseEvidence').click();assert.equal(await page.evaluate(()=>document.activeElement.id),'coverage-review-'+rowIds[0]);
  await openRow(page.locator('#coverageRows button').nth(1));await page.getByRole('button',{name:'Draft questions for review',exact:true}).click();await cards();await review(0,'Reject proposal','rejected');
  checks.push('shared_coverage_source_two_row_drafts_multiple_proposals_approved_rejected_unreviewed_focus_and_source_links');
  step='select_export';
  const opts=await (await context.request.get(origin+base+'/export-options?coverage_export_revision_id='+source)).json();
  assert.equal(opts.draft_revisions.length,2);assert.ok(opts.draft_revisions.every(d=>d.source_export_revision_id===source));
  for(const row of rowIds){const d=opts.draft_revisions.find(d=>d.selected_row_ids.includes(row));await page.getByLabel('Draft for '+row,{exact:true}).selectOption(d.recommendation_revision_id);await page.getByLabel('Review for '+row,{exact:true}).selectOption(d.latest_review_revision_id);}
  await page.locator('#coverageCheckRunExport').click();await page.waitForFunction(()=>!document.getElementById('coveragePrepareRunExport').disabled);
  assert.match(await page.locator('.coverage-export-summary').textContent(),/918 source rows/);assert.match(await page.locator('.coverage-export-summary').textContent(),/2 rows with selected draft revisions/);
  await page.locator('#coveragePrepareRunExport').click();await page.getByRole('link',{name:'Download run CSV',exact:true}).waitFor();
  const csvUrl=await page.getByRole('link',{name:'Download run CSV',exact:true}).getAttribute('href'),manifestUrl=await page.getByRole('link',{name:'Matching manifest',exact:true}).getAttribute('href');
  const downloadPromise=page.waitForEvent('download');await page.getByRole('link',{name:'Download run CSV',exact:true}).click();await (await downloadPromise).saveAs(path.join(output,'synthetic-a5-run.csv'));
  const bytes=fs.readFileSync(path.join(output,'synthetic-a5-run.csv')),manifest=await (await context.request.get(origin+manifestUrl)).json();
  assert.equal(manifest.row_count,918);assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),manifest.csv_sha256);assert.equal(Object.keys(manifest.revision_selection_map).length,2);assert.ok(bytes.subarray(0,3).equals(Buffer.from([239,187,191])));
  assert.equal(manifest.summary.recommendation_review_states.approved,1);assert.equal(manifest.summary.recommendation_review_states.rejected,1);assert.equal(manifest.summary.recommendation_review_states.unreviewed,2);
  fs.writeFileSync(path.join(output,'synthetic-a5-manifest.json'),JSON.stringify(manifest),{mode:0o600});
  await review(0,'Request changes','needs changes');assert.deepEqual(await (await context.request.get(origin+csvUrl)).body(),bytes);
  checks.push('explicit_per_row_draft_review_selection_918_bom_csv_matching_manifest_and_old_bytes_after_new_review');
  step='incompatible';await page.locator('#coverageFreezeSource').click();await page.waitForFunction(old=>document.getElementById('coverageExportSource').value!==old,source);
  assert.match(await page.locator('#coverageRunExport').textContent(),/Different coverage source/);assert.equal(await page.getByLabel('Draft for '+rowIds[0],{exact:true}).locator('option').count(),1);
  await page.locator('#coverageExportSource').selectOption(source);await page.waitForFunction(row=>document.querySelector('select[aria-label="Draft for '+row+'"]')?.options.length===2,rowIds[0]);
  checks.push('incompatible_source_drafts_disclosed_not_silently_merged');
  step='stale_row';
  const delayedPattern='**/runs/'+run+'/rows/'+rowIds[0];let intercepted=false;
  await page.route(delayedPattern,async route=>{intercepted=true;await new Promise(r=>setTimeout(r,700));await route.continue();});
  await page.locator('#coverageRows button').first().click();await page.waitForTimeout(80);await page.locator('#coverageRows button').nth(1).click();await page.locator('.coverage-selected-query').waitFor();await page.waitForTimeout(900);
  assert.ok(intercepted);assert.match(await page.locator('.coverage-selected-query').textContent(),/پرسش دوم/);await page.unroute(delayedPattern);
  const recommendationRequests=requests.filter(p=>/\/recommendations\/rec_/.test(p)).length;await page.locator('#coverageCloseEvidence').click();await page.waitForTimeout(1300);assert.equal(requests.filter(p=>/\/recommendations\/rec_/.test(p)).length,recommendationRequests);
  // A delayed old run-progress response must not repaint the newly selected run.
  step='stale_run';const runs=await (await context.request.get(origin+'/api/knowledge-coverage/runs')).json();const older=runs.find(r=>r.input_row_count===3);assert.ok(older);
  const oldPattern='**/api/knowledge-coverage/runs/'+older.run_id;
  await page.route(oldPattern,async route=>{await new Promise(r=>setTimeout(r,700));await route.continue();});
  await page.locator('#coverageRuns').selectOption(older.run_id);await page.waitForTimeout(80);await page.locator('#coverageRuns').selectOption(run);await page.waitForTimeout(1000);
  assert.match(await page.locator('#coverageProgressText').textContent(),/918 rows retained/);await page.unroute(oldPattern);
  checks.push('delayed_row_and_run_responses_cannot_replace_selection_detached_panel_polling_stops');
  step='screenshots';await page.locator('#coverageFilter').selectOption('possible_partial_gap');await page.waitForFunction(()=>document.querySelectorAll('#coverageRows button').length===2);await openRow(page.locator('#coverageRows button').nth(1));await cards();
  for(const [width,theme,dir] of [[1440,'dark','ltr'],[1440,'light','rtl'],[1280,'dark','rtl'],[1280,'light','ltr'],[768,'dark','ltr'],[768,'light','rtl'],[390,'dark','rtl'],[390,'light','ltr']]){
   step='layout_'+width+'_'+theme+'_'+dir;await page.setViewportSize({width,height:width===390?844:1000});
   const light=await page.locator('body').evaluate(el=>el.classList.contains('light-mode'));if(light!==(theme==='light'))await page.locator('#coverageTheme').click();
   if(await page.locator('html').getAttribute('dir')!==dir)await page.locator('#coverageLanguage').click();
   assert.equal(await page.locator('html').getAttribute('lang'),'en');
   const scroll=page.locator('.coverage-table-scroll').last();
   if(await scroll.evaluate(el=>el.scrollWidth>el.clientWidth+2)){
    await scroll.scrollIntoViewIfNeeded();await scroll.focus();await scroll.evaluate(el=>{el.scrollLeft=0;});
    await page.keyboard.press(dir==='rtl'?'ArrowLeft':'ArrowRight');await page.waitForTimeout(150);
    assert.ok(Math.abs(await scroll.evaluate(el=>el.scrollLeft))>0);
   }
   await page.locator('.recommendation-card').first().scrollIntoViewIfNeeded();
   const selectedBox=await page.locator('.coverage-selected-query > strong').boundingBox(),bar=await page.locator('.topbar').boundingBox();assert.ok(selectedBox.y>=bar.y+bar.height-1);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
   const focus=page.locator('#coverage-detail-nav a'); // actual visible focus also checked on a real control below.
   await page.locator('#coverageCloseEvidence').focus();assert.ok(await page.locator('#coverageCloseEvidence').evaluate(el=>parseFloat(getComputedStyle(el).outlineWidth)>=3));
   await shot('a5-'+width+'-'+theme+'-'+dir+'.png');
  }
  await page.setViewportSize({width:1440,height:1000});
  if(!await page.locator('body').evaluate(el=>el.classList.contains('light-mode')))await page.locator('#coverageTheme').click();
  if(await page.locator('html').getAttribute('dir')!=='ltr')await page.locator('#coverageLanguage').click();
  step='populated_export_screenshot';await page.locator('#coverageExportSource').selectOption(source);
  await page.waitForFunction(row=>document.querySelector('select[aria-label="Draft for '+row+'"]')?.options.length===2,rowIds[0]);
  for(const row of rowIds){const d=opts.draft_revisions.find(d=>d.selected_row_ids.includes(row));await page.getByLabel('Draft for '+row,{exact:true}).selectOption(d.recommendation_revision_id);await page.getByLabel('Review for '+row,{exact:true}).selectOption(d.latest_review_revision_id);}
  await page.locator('#coverageCheckRunExport').click();await page.waitForFunction(()=>!document.getElementById('coveragePrepareRunExport').disabled);
  await page.locator('#coverageRunExport').screenshot({path:path.join(output,'a5-run-selection-light.png')});screenshots.push('a5-run-selection-light.png');
  step='proposal_review_screenshot';await openRow(page.locator('#coverageRows button').first());await cards();
  await page.locator('.recommendation-card').first().scrollIntoViewIfNeeded();await shot('a5-proposal-review-light.png');
  checks.push('actual_390_768_1280_1440_light_dark_rtl_ltr_screenshots_no_page_overflow_visible_focus');
  assert.equal(pageErrors,0);assert.ok(!requests.some(p=>/chunks\/(create|update|delete|revert)|chat\/completions|\/tokenize/.test(p)));
  checks.push('no_page_errors_no_kb_writes_no_real_model_dispatches');
  const summary={browser_version:browser.version(),checks,screenshots,source_rows:918,pilot_selected:5,model_dispatches:0,independent_human_labels:'not_reviewed'};
  fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify(summary,null,2),{mode:0o600});for(const n of fs.readdirSync(output))fs.chmodSync(path.join(output,n),0o600);process.stdout.write(JSON.stringify(summary)+'\n');
 }catch(error){await page.screenshot({path:path.join(output,'synthetic-failure.png')});fs.writeFileSync(path.join(output,'failure-diagnostics.json'),JSON.stringify({step,pageErrors,safePageErrors,status:await page.locator('#coverageStatus').textContent(),error:await page.locator('#coverageError').textContent(),progress:await page.locator('#coverageProgressText').textContent()}),{mode:0o600});throw error;}finally{await browser.close();}
}
run().catch(error=>{process.stderr.write(JSON.stringify({status:'synthetic_browser_check_failed',step,category:error.name})+'\n');process.exitCode=1;});
