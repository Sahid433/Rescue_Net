document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.flash').forEach(el=>{setTimeout(()=>{if(el.isConnected)el.classList.add('fade-out')},6000)});
  document.querySelectorAll('form').forEach(form=>form.addEventListener('submit',()=>{
    const btn=form.querySelector('button[type="submit"],button:not([type])');
    if(btn && !btn.dataset.noLoading){btn.dataset.original=btn.innerHTML;btn.innerHTML='Working…';}
  }));
});
