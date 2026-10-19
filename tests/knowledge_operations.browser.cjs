/* Isolated actual Chromium, exclusively synthetic/mocked 918-row budget flow. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const local=require('node:module').createRequire(path.resolve(process.argv[2],'package.json'));
const {chromium:engine}=local('playwright'),mod=local('@sparticuz/chromium'),chromium=mod.default||mod;
const origin=process.argv[3],output=path.resolve(process.argv[4]);assert.equal(new URL(origin).hostname,'127.0.0.1');fs.mkdirSync(output,{recursive:true,mode:0o700});
async function run(){
 chromium.setGraphicsMode=false;const browser=await engine.launch({executablePath:await chromium.executablePath(),args:[...chromium.args,'--disable-gpu'],headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true,reducedMotion:'reduce'}),page=await context.newPage();let errors=0;page.on('pageerror',()=>errors++);
 await context.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
 async function shot(name){await page.screenshot({path:path.join(output,name)});}
 async function download(selector){const ready=page.waitForEvent('download');await page.locator(selector).click();return fs.readFileSync(await(await ready).path());}
 try{
 assert.equal((await context.request.post(origin+'/api/login',{data:{username:'planner-synthetic',password:'synthetic-browser-only'}})).status(),200);
 await page.goto(origin+'/knowledge-coverage');await page.locator('#coverageRoot').waitFor();
 const csv='\ufeffquery\r\n'+Array(918).fill('"پرسش آزمایشی، نیم‌فاصله و زمان تأیید کارت خیالی؟\nSynthetic duration and cutoff?"').join('\r\n')+'\r\n';
 await page.locator('#coverageFile').setInputFiles({name:'synthetic-a62-918.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
 await page.waitForFunction(()=>document.getElementById('coverageQueryColumn').value==='query');await page.locator('#coverageUpload').click();
 await page.waitForFunction(()=>document.querySelectorAll('#coverageRows input').length===25);
 await page.locator('#coverageSnapshot').selectOption({label:await page.locator('#coverageSnapshot option').filter({hasText:'2 entries'}).textContent()});
 await page.locator('#coverageMode').selectOption('full_input');assert.equal(await page.locator('#coverageStart').isDisabled(),true);
 await page.getByText('Finite execution limits',{exact:true}).click();await page.locator('#coverageLimit_completion_attempts').fill('2');await page.locator('#coverageLimit_completion_attempts').dispatchEvent('change');
 await page.locator('#coverageBudgetAck').check();await page.locator('#coverageSizingAckLabel').waitFor();await page.locator('#coverageSizingAck').check();
 await page.locator('#coverageStart').focus();await page.keyboard.press('Enter');
 await page.waitForFunction(()=>document.getElementById('coverageProgressText').textContent.startsWith('Paused'),{},{timeout:30000});
 assert.match(await page.locator('#coverageBudgetProgress').textContent(),/0 remaining/);assert.match(await page.locator('#coverageProgressText').textContent(),/0 of 918/);
 const rid=await page.locator('#coverageRuns').inputValue(),url='/api/knowledge-coverage/runs/'+rid;
 await page.locator('#coverageResume').click();await page.waitForFunction(()=>document.getElementById('coverageError').textContent.includes('budget_new_run_required'));
 const live=await(await context.request.get(origin+url)).json();assert.equal(live.state,'paused');assert.equal(live.operational_budget.completion_attempts,2);assert.equal(live.pending_rows,918);
 if(!await page.locator('body').evaluate(e=>e.classList.contains('light-mode')))await page.locator('#coverageTheme').click();
 await page.locator('#coverageProgressText').scrollIntoViewIfNeeded();await shot('a62-paused-light.png');
 await page.locator('.coverage-legacy-download summary').click();await page.locator('#coveragePrepareExport').click();await page.locator('#coverageExport:visible').waitFor();
 const csvBytes=await download('#coverageExport'),manifest=JSON.parse(await download('#coverageManifest'));
 assert.equal(manifest.row_count,918);assert.equal(manifest.state,'paused');assert.equal(manifest.operational_budget.remaining_completions,0);assert.equal(manifest.operational_budget.unknown_reservations,0);
 assert.equal(crypto.createHash('sha256').update(csvBytes).digest('hex'),manifest.csv_sha256);
 const again=await context.request.get(origin+url+'/export?revision_id='+manifest.export_revision_id);assert.deepEqual(await again.body(),csvBytes);
 // Continue the paused run: a linked subset over its 918 unfinished rows, then one export of the whole input.
 await page.locator('#coverageContinue:visible').waitFor();assert.equal(await page.locator('#coverageContinue').textContent(),'Continue unfinished rows (918)');
 await page.locator('#coverageContinueSizingAckLabel').waitFor();assert.equal(await page.locator('#coverageContinue').isDisabled(),true);
 await page.locator('#coverageContinueSizingAck').check();await page.locator('#coverageContinue').click();
 await page.waitForFunction(old=>document.getElementById('coverageRuns').value!==old,rid);const next=await page.locator('#coverageRuns').inputValue();
 await page.waitForFunction(()=>document.getElementById('coverageProgressText').textContent.startsWith('Paused'),{},{timeout:30000});
 const continued=await(await context.request.get(origin+'/api/knowledge-coverage/runs/'+next)).json();
 assert.equal(continued.continues_run_id,rid);assert.equal(continued.chain_root_run_id,rid);assert.equal(continued.execution_mode,'subset');assert.equal(continued.selected_row_ids.length,918);
 await page.locator('#coverageChainExport:visible').waitFor();const chainBytes=await download('#coverageChainExport');
 const chainManifest=await(await context.request.get(origin+await page.locator('#coverageChainManifest').getAttribute('href'))).json();
 assert.deepEqual(chainManifest.chain_run_ids,[rid,next]);assert.equal(chainManifest.row_count,918);assert.equal(chainManifest.chain_export_version,'coverage-chain-export-1');
 assert.equal(crypto.createHash('sha256').update(chainBytes).digest('hex'),chainManifest.csv_sha256);
 await page.locator('#coverageLanguage').click();await page.locator('#coverageTheme').click();await page.setViewportSize({width:390,height:844});
 await page.locator('#coverageBudgetProgress').scrollIntoViewIfNeeded();await shot('a62-paused-dark-rtl.png');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
 assert.equal(errors,0);
 const report={browser_version:browser.version(),synthetic_rows:918,live_dispatches:0,checks:['explicit_full_budget_acknowledgement_and_keyboard_start','durable_two_call_pause_zero_missing_gap_and_918_pending','exhausted_recovery_refused_without_reset','immutable_918_csv_manifest_hash_and_allowance','continue_paused_run_linked_subset_and_chain_export_hash','light_dark_keyboard_and_390_rtl_no_page_overflow'],screenshots:['a62-paused-light.png','a62-paused-dark-rtl.png']};
 fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify(report,null,2));process.stdout.write(JSON.stringify(report)+'\n');
 }finally{await browser.close();}
}
run().catch(error=>{process.stderr.write(error.name+': '+error.message+'\n');process.exitCode=1;});
