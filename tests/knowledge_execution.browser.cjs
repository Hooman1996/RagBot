/* Actual isolated Chromium, synthetic 918-row upload and mocked inference only. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const local=require('node:module').createRequire(path.resolve(process.argv[2],'package.json'));
const {chromium:engine}=local('playwright'),mod=local('@sparticuz/chromium'),chromium=mod.default||mod;
const origin=process.argv[3],output=path.resolve(process.argv[4]);assert.equal(new URL(origin).hostname,'127.0.0.1');fs.mkdirSync(output,{recursive:true,mode:0o700});
let step='start';const checks=[],screenshots=[];
async function run(){
 chromium.setGraphicsMode=false;
 const browser=await engine.launch({executablePath:await chromium.executablePath(),args:[...chromium.args,'--disable-gpu'],headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true,reducedMotion:'reduce'}),page=await context.newPage();
 let errors=0;page.on('pageerror',()=>errors++);
 await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 async function shot(name){await page.screenshot({path:path.join(output,name)});screenshots.push(name);}
 async function download(selector){const pending=page.waitForEvent('download');await page.locator(selector).click();return fs.readFileSync(await (await pending).path());}
 try{
  step='upload';assert.equal((await context.request.post(origin+'/api/login',{data:{username:'planner-synthetic',password:'synthetic-browser-only'}})).status(),200);
  await page.goto(origin+'/knowledge-coverage');await page.locator('#coverageRoot[data-contract="coverage-page-3"]').waitFor();
  assert.equal(await page.locator('#coverageMode').inputValue(),'pilot');
  if(!await page.locator('body').evaluate(e=>e.classList.contains('light-mode')))await page.locator('#coverageTheme').click();
  const questions=Array(918).fill('Synthetic approval duration and cutoff? پرسش آزمایشی با نیم‌فاصله، "نقل قول"\nخط دوم؟');questions[0]='Interrupt synthetic approval duration and cutoff?';questions[7]='';
  const csv='\ufeffquery\r\n'+questions.map(q=>'"'+q.replaceAll('"','""')+'"').join('\r\n')+'\r\n';
  await page.locator('#coverageFile').setInputFiles({name:'synthetic-a61-918.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
  await page.waitForFunction(()=>document.getElementById('coverageQueryColumn').value==='query');await page.locator('#coverageUpload').click();
  await page.waitForFunction(()=>document.querySelectorAll('#coverageRows input[type=checkbox]').length===25);
  await page.locator('#coverageSnapshot').selectOption({label:await page.locator('#coverageSnapshot option').filter({hasText:'2 entries'}).textContent()});
  await page.waitForFunction(()=>!document.getElementById('coverageDatasetSummary').textContent.includes('Preparing input'));
  step='full_selection';await page.locator('#coverageMode').selectOption('full_input');
  await page.waitForFunction(()=>document.getElementById('coverageStartSummary').textContent.includes('918 / 918'));
  await page.waitForFunction(()=>document.querySelectorAll('#coverageRows input[type=checkbox]:disabled:checked').length===25);
  await page.locator('#coverageStart').focus();assert.equal(await page.locator('#coverageStart').evaluate(e=>document.activeElement===e),true);
  await shot('a61-full-input-light.png');
  await page.keyboard.press('Enter');await page.waitForFunction(()=>document.getElementById('coverageProgressText').textContent.includes('918 selected questions'));
  const first=await page.locator('#coverageRuns').inputValue();const url='/api/knowledge-coverage/runs/'+first;
  const meta=await (await context.request.get(origin+url)).json();assert.equal(meta.selected_rows,918);assert.equal(meta.execution_mode,'full_input');
  step='cancel_unknown';await page.locator('#coverageCancel').click();await page.waitForFunction(()=>document.getElementById('coverageProgressText').textContent.startsWith('Cancelled'));
  await page.waitForFunction(()=>document.getElementById('coverageRecoveryText').textContent.startsWith('1 request'));
  await page.locator('#coverageResume').click();await page.waitForFunction(()=>document.getElementById('coverageError').textContent.includes('unknown_remote_completion_requires_choice'));
  await shot('a61-recovery-light.png');
  checks.push('918_server_resolved_full_selection_default_pilot_and_unknown_remote_retry_blocked');
  step='explicit_retry';await page.locator('#coverageRecoveryChoice').selectOption('retry_unknown');await page.locator('#coverageResume').click();
  await page.waitForFunction(()=>Number(document.getElementById('coverageProgress').value)>=2,{},{timeout:30000});
  await page.locator('#coverageCancel').click();await page.waitForFunction(()=>document.getElementById('coverageProgressText').textContent.startsWith('Cancelled'));
  step='immutable_partial_export';await page.locator('.coverage-legacy-download summary').click();await page.locator('#coveragePrepareExport').click();await page.locator('#coverageExport:visible').waitFor();
  const body=await download('#coverageExport'),manifest=JSON.parse(await download('#coverageManifest'));
  assert.equal(manifest.row_count,918);assert.equal(manifest.input_scope,'full_input');assert.equal(manifest.state,'cancelled');assert.equal(crypto.createHash('sha256').update(body).digest('hex'),manifest.csv_sha256);
  const again=await context.request.get(origin+url+'/export?revision_id='+manifest.export_revision_id);assert.deepEqual(await again.body(),body);
  checks.push('explicit_duplicate_work_acknowledgement_checkpoint_resume_cancel_and_immutable_918_row_export');
  step='larger_subset';const dataset=await page.locator('#coverageDataset').inputValue();await page.locator('#coverageDataset').selectOption(dataset);
  await page.waitForFunction(()=>document.querySelectorAll('#coverageRows input[type=checkbox]').length===25);
  await page.locator('#coverageMode').selectOption('subset');
  await page.waitForFunction(()=>document.querySelectorAll('#coverageRows input[type=checkbox]').length===25 && document.querySelectorAll('#coverageRows input[type=checkbox]:disabled').length===0 && document.querySelectorAll('#coverageRows input[type=checkbox]:checked').length===0);
  for(let i=1;i<=9;i++)await page.locator('#coverageRows input[type=checkbox]').nth(i).check();
  step='subset_selection_count';assert.match(await page.locator('#coverageStartSummary').textContent(),/9 \/ 918/);
  await page.locator('#coverageStart').click();await page.waitForFunction(()=>document.getElementById('coverageProgressText').textContent.startsWith('completed'),{},{timeout:30000});
  step='subset_finished_counts';assert.match(await page.locator('#coverageProgressText').textContent(),/9 of 9 selected questions/);assert.match(await page.locator('#coverageProgressText').textContent(),/with errors/);
  const second=await page.locator('#coverageRuns').inputValue();assert.notEqual(first,second);
  await page.locator('#coverageRows button').nth(1).click();await page.locator('.coverage-selected-query').waitFor();
  await page.locator('#coverageLanguage').click();await page.locator('#coverageTheme').click();await page.setViewportSize({width:390,height:844});
  await page.locator('#coverageProgressText').scrollIntoViewIfNeeded();await shot('a61-subset-dark-rtl.png');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('#coverageCloseEvidence').focus();await page.keyboard.press('Enter');
  checks.push('nine_row_subset_finished_with_errors_evidence_keyboard_dark_rtl_mobile_no_overflow');
  assert.equal(errors,0);
  const summary={browser_version:browser.version(),source_rows:918,subset_rows:9,live_model_dispatches:0,checks,screenshots};
  fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify(summary,null,2),{mode:0o600});for(const name of fs.readdirSync(output))fs.chmodSync(path.join(output,name),0o600);process.stdout.write(JSON.stringify(summary)+'\n');
 }catch(error){await shot('synthetic-failure.png');fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({step,error:await page.locator('#coverageError').textContent(),progress:await page.locator('#coverageProgressText').textContent(),recovery:await page.locator('#coverageRecoveryText').textContent(),selection:await page.locator('#coverageStartSummary').textContent(),checked:await page.locator('#coverageRows input[type=checkbox]:checked').count(),mode:await page.locator('#coverageMode').inputValue()}),{mode:0o600});throw error;}finally{await browser.close();}
}
run().catch(error=>{process.stderr.write(JSON.stringify({status:'synthetic_browser_check_failed',step,category:error.name})+'\n');process.exitCode=1;});
