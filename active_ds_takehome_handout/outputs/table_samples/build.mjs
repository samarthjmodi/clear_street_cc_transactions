import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const out = fileURLToPath(new URL('.', import.meta.url));
const root = fileURLToPath(new URL('../../', import.meta.url));
const wb = Workbook.create();
const manifests=[];
const names = {'master — all columns':'master','master — 10 nontransactor examples (selected columns)':'master_no_transactions','demographics_by_observation.csv':'demographics','activity_distributions.csv':'activity_distributions','merchant_categories.csv':'merchant_categories'};
function letter(n) { let s=''; for(n++;n>0;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s; return s; }
for(const file of ['analysis/table_samples.md','analysis/output_samples.md']) {
 const text=await fs.readFile(root+file,'utf8');
 for(const section of text.split('\n## ').slice(1)) {
  const lines=section.split('\n'); const title=lines[0];
  const table=lines.slice(1).filter(x=>x.includes(' | '));
  const headers=table[0].split(' | '); if(!headers[0])headers[0]='metric';
  const rows=table.slice(2).map(x=>x.split(' | ').map(v=>v==='∅'?null:v.replaceAll('\\|','|')));
  const name=names[title]??title.replace(/\.(csv|json)$/,'');
  const sh=wb.worksheets.add(name);sh.showGridLines=false;
  const dates=new Set();const money=new Set();
  const typed=rows.map(row=>row.map((v,i)=>{
   if(v===null)return null;
   const h=headers[i];
   if(/(^id$|_id$|^mcc$|_mcc$|^zip$|_zip$|card_number|cvv)/.test(h))return v;
   if(/^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$/.test(v)){dates.add(i);return new Date(v.replace(' ','T')+(v.includes(' ')?'Z':'T00:00:00Z'));}
   if(/^\$-?\d+(\.\d+)?$/.test(v)){money.add(i);return Number(v.slice(1));}
   if(/^-?\d+(\.\d+)?$/.test(v))return Number(v);
   return v;
  }));
  const range=sh.getRangeByIndexes(0,0,rows.length+1,headers.length);
  range.values=[headers,...typed];range.format.font={name:'Arial',size:10};
  range.format.rowHeight=32;range.format.verticalAlignment='center';
  const header=sh.getRangeByIndexes(0,0,1,headers.length);
  header.format.fill='#203A54';header.format.font={name:'Arial',size:10,bold:true,color:'#FFFFFF'};
  header.format.wrapText=true;header.format.rowHeight=66;
  for(let i=0;i<headers.length;i++){
   const max=Math.max(headers[i].length,...rows.map(r=>String(r[i]??'').length));
   const col=sh.getRangeByIndexes(0,i,rows.length+1,1);col.format.columnWidth=Math.min(46,Math.max(17,max*.8+2));
   const body=sh.getRangeByIndexes(1,i,rows.length,1);body.format.wrapText=true;
   if(dates.has(i))body.setNumberFormat('yyyy-mm-dd hh:mm:ss');
   else if(money.has(i))body.setNumberFormat('$#,##0.00');
   else if(typed.some(r=>typeof r[i]==='number'))body.setNumberFormat(typed.some(r=>typeof r[i]==='number'&&!Number.isInteger(r[i]))?'#,##0.00':'#,##0');
  }
  for(let r=2;r<=rows.length;r+=2)sh.getRangeByIndexes(r,0,1,headers.length).format.fill='#F0F4F8';
  sh.freezePanes.freezeRows(1);if(headers.length>8)sh.freezePanes.freezeColumns(1);
  const noteRow=rows.length+3;
  sh.getRangeByIndexes(noteRow,0,1,1).values=[['Sample only; up to 10 rows. Blank = missing. Card number/CVV masked.']];
  manifests.push({name,rows:rows.length,columns:headers.length});
 }
}
wb.recalculate();
console.log((await wb.inspect({kind:'sheet',include:'id,name',maxChars:4000})).ndjson);
for(const m of manifests){
 const p=await wb.render({sheetName:m.name,range:`A1:${letter(Math.min(m.columns,6)-1)}${m.rows+1}`,scale:1,format:'png'});
 await fs.writeFile(out+m.name+'.png',new Uint8Array(await p.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);await xlsx.save(out+'Clear_Street_Table_Samples.xlsx');
await fs.writeFile(out+'manifest.json',JSON.stringify(manifests,null,2));
console.log(JSON.stringify({sheets:manifests.length,file:out+'Clear_Street_Table_Samples.xlsx'}));
