'use strict';
(() => {
  const config=JSON.parse(document.getElementById('speech-config').textContent);
  const $=id=>document.getElementById(id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let experiments=[],current=null,chosen=[],serial=0;
  const cache=new Map();
  const status=(text,error=false)=>{$('speech-status').textContent=text;$('speech-status').hidden=!text;$('speech-status').classList.toggle('error',error);};
  async function request(path,payload){
    const r=await fetch('/api/speech/'+path,payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await r.json();if(!r.ok)throw new Error(data.error||'Не удалось загрузить результаты.');return data;
  }
  async function refresh(){
    const previous=current?.key;
    const [result,notes]=await Promise.all([request('experiments?lab='+config.lab),request('notes?lab='+config.lab)]);
    experiments=result.experiments;
    $('lab-conclusions').innerHTML=notes.notes.split(/\n\s*\n/).filter(Boolean).map(p=>`<p>${esc(p)}</p>`).join('');
    $('conclusions-panel').hidden=!notes.notes.trim();
    $('experiment-select').innerHTML=experiments.length?experiments.map(e=>`<option value="${esc(e.key)}">${esc(e.title)}</option>`).join(''):'<option value="">Опыты ещё не подготовлены</option>';
    if(previous&&experiments.some(e=>e.key===previous))$('experiment-select').value=previous;
    select();status('');
  }
  function select(){
    document.querySelectorAll('#experiment-result audio').forEach(a=>a.pause());
    current=experiments.find(e=>e.key===$('experiment-select').value);
    if(!current){$('experiment-result').innerHTML='<p class="muted">Нет результатов.</p>';return;}
    chosen=current.items.slice(0,2).map(i=>i.id);serial++;
    $('result-observation').value=current.observations||'';
    const rows=current.items.map(item=>{
      const m=item.measurement||{};
      return `<tr><td><label class="speech-inline"><input type="checkbox" data-result-choose="${item.id}" ${chosen.includes(item.id)?'checked':''}><span>${esc(item.role)}</span></label>
      <small class="result-format">${m.sample_rate||''} Гц · ${m.bits||''} бит · ${m.size_bytes?Number(m.size_bytes/1024).toFixed(1)+' КБ':''}</small></td>
      <td>${Number(m.duration||0).toFixed(3)} с</td><td>F₀: ${m.median_f0?Number(m.median_f0).toFixed(1)+' Гц':'—'}<br>RMS: ${m.rms===undefined?'—':Number(m.rms).toFixed(4)}</td>
      <td><audio controls preload="metadata" src="/api/speech/wav/${item.id}" aria-label="${esc(item.role)}"></audio></td>
      <td><a href="/api/speech/wav/${item.id}">WAV</a><br><a href="/api/speech/measurements/${item.id}">CSV</a></td></tr>`;
    }).join('');
    const metrics=(current.metrics||[]).map(m=>`<span>${esc(m)}</span>`).join('');
    $('experiment-result').innerHTML=`<h2>${esc(current.title)}</h2><p>${esc(current.description)}</p>
      ${metrics?`<div class="result-meta">${metrics}</div>`:''}
      ${current.transcription?`<p class="speech-transcription"><strong>Транскрипция:</strong> ${esc(current.transcription)}</p>`:''}
      <div class="table-scroll"><table class="results-table"><thead><tr><th>Вариант / график</th><th>Длительность</th><th>Измерения</th><th>Прослушать</th><th>Скачать</th></tr></thead><tbody>${rows}</tbody></table></div>
      ${current.finding?`<p class="speech-method-note">${esc(current.finding)}</p>`:''}
      ${current.recipe?`<details><summary>Параметры опыта</summary><pre class="speech-recipe">${esc(current.recipe)}</pre></details>`:''}`;
    $('result-charts').innerHTML='';
    if($('result-plots').open)charts().catch(e=>status(e.message,true));
  }
  async function charts(){
    const ticket=++serial;
    if(!current||!chosen.length){$('result-charts').innerHTML='';return;}
    $('result-charts').innerHTML='<p class="muted">Вычисляю графики…</p>';
    const data=await Promise.all(chosen.map(async id=>{
      if(!cache.has(id))cache.set(id,await request('analysis/'+id));
      return{id,data:cache.get(id),role:current.items.find(i=>i.id===id)?.role||String(id)};
    }));
    if(ticket!==serial)return;
    const duration=Math.max(...data.map(x=>x.data.end)),amplitude=Math.max(.001,...data.map(x=>x.data.peak))*1.08;
    const rmsMax=Math.max(.001,...data.flatMap(x=>x.data.energy))*1.08;
    $('result-charts').innerHTML=data.map((item,i)=>`<article class="result-chart"><h3>${esc(item.role)}</h3><canvas id="result-wave-${i}" width="1050" height="190" aria-label="Осциллограмма ${esc(item.role)}"></canvas><canvas id="result-pitch-${i}" width="1050" height="190" aria-label="Контуры ${esc(item.role)}"></canvas>
      <div class="speech-toolbar"><a href="/api/speech/plot/${item.id}?kind=wave">Осциллограмма SVG</a><a href="/api/speech/plot/${item.id}?kind=contours">Контуры SVG</a></div></article>`).join('');
    data.forEach((item,i)=>{plot($('result-wave-'+i),item.data,duration,amplitude,rmsMax,false);plot($('result-pitch-'+i),item.data,duration,amplitude,rmsMax,true);});
  }
  function plot(canvas,data,duration,amplitude,rmsMax,contours){
    const c=canvas.getContext('2d'),l=65,r=canvas.width-18,t=25,b=canvas.height-30;
    c.fillStyle='#fff';c.fillRect(0,0,canvas.width,canvas.height);c.font='12px system-ui';
    const tx=s=>l+(r-l)*s/duration;
    for(let i=0;i<=4;i++){
      const y=t+(b-t)*i/4;c.strokeStyle='#dce5e8';c.beginPath();c.moveTo(l,y);c.lineTo(r,y);c.stroke();
      c.fillStyle='#61747c';c.fillText(contours?String(500-i*125):((1-i/2)*amplitude).toFixed(3),4,y+4);
    }
    for(let i=0;i<=5;i++){c.fillStyle='#61747c';c.fillText((duration*i/5).toFixed(2)+' с',l+(r-l)*i/5-15,canvas.height-8);}
    if(!contours){
      c.fillStyle='#61747c';c.fillText('Амплитуда PCM · общая шкала',l,15);c.strokeStyle='#087b89';c.beginPath();
      data.wave.low.forEach((lo,i)=>{const x=tx(data.start+(data.end-data.start)*(i+.5)/data.wave.low.length);c.moveTo(x,t+(1-data.wave.high[i]/amplitude)*(b-t)/2);c.lineTo(x,t+(1-lo/amplitude)*(b-t)/2);});c.stroke();
    }else{
      for(const[values,max,color]of[[data.f0,500,'#087b89'],[data.energy,rmsMax,'#ba5b28']]){
        c.strokeStyle=color;c.lineWidth=1.6;c.beginPath();let drawing=false;
        values.forEach((value,i)=>{if(value===null){drawing=false;return;}const x=tx(data.times[i]),y=b-(b-t)*Math.min(value/max,1);if(drawing)c.lineTo(x,y);else c.moveTo(x,y);drawing=true;});c.stroke();
      }
      c.fillStyle='#087b89';c.fillText('F₀: 0–500 Гц',l,15);c.fillStyle='#ba5b28';c.fillText('RMS: 0–'+rmsMax.toFixed(3),l+190,15);
    }
  }
  $('experiment-select').addEventListener('change',select);
  $('result-plots').addEventListener('toggle',()=>{if($('result-plots').open)charts().catch(e=>status(e.message,true));});
  $('experiment-result').addEventListener('change',e=>{
    const input=e.target.closest('[data-result-choose]');if(!input)return;
    const id=Number(input.dataset.resultChoose);
    if(input.checked&&chosen.length>=4){input.checked=false;status('Для наглядности выберите не более четырёх записей.',true);return;}
    chosen=input.checked?[...chosen,id]:chosen.filter(n=>n!==id);
    if($('result-plots').open)charts().catch(e=>status(e.message,true));
  });
  $('result-observation-save').addEventListener('click',async()=>{
    if(!current)return;
    try{await request('observe',{key:current.key,observations:$('result-observation').value});current.observations=$('result-observation').value;status('Сохранено.');}
    catch(e){status(e.message,true);}
  });
  document.addEventListener('play',e=>{
    if(e.target.tagName==='AUDIO')document.querySelectorAll('audio').forEach(a=>{if(a!==e.target)a.pause();});
  },true);
  refresh().catch(e=>status(e.message,true));
})();
