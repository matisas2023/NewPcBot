// No browser, network, credentials or real pointer: verify gesture math and offline discard.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

module.exports = async function testTouchpad() {
  const nodes = new Map(), calls = [];
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {id, value:'', hidden:false, disabled:false, handlers:{},
      classList:{values:new Set(),toggle(name,value){if(value)this.values.add(name);else this.values.delete(name);},contains(name){return this.values.has(name);}}, addEventListener(name,fn){this.handlers[name]=fn;},
      setAttribute(){}, setPointerCapture(){}, replaceChildren(){}, removeAttribute(){}, close(){this.open=false;}, showModal(){this.open=true;},
      querySelector(){return node('submit');}});
    return nodes.get(id);
  }
  const context = vm.createContext({
    document:{getElementById:node, querySelectorAll:()=>[], addEventListener(){}, hidden:false},
    window:{addEventListener(){},isSecureContext:false}, history:{replaceState(){},pushState(){},state:{}},
    navigator:{}, URL, Blob, AbortSignal, Date, console, setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},
    fetch:async (url,options) => {
      const payload = options.body ? JSON.parse(options.body) : null;
      calls.push({url,payload});
      const body = url.endsWith('session') ? {csrf:'fixture'} : url.endsWith('connection') ? {tunnel:{state:'local'}} : {pc:'demo',os:'test',cpu:1,ram:2,disk:3,uptime:1};
      return {ok:true,status:200,json:async()=>body};
    }
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../pc_remote/web/app.js'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("loggedIn=true; online=true; activeTab='control';",context);
  const pad=node('touchpad');
  pad.handlers.pointerdown({pointerId:1,clientX:10,clientY:10,preventDefault(){}});
  pad.handlers.pointermove({pointerId:1,clientX:30,clientY:20});
  pad.handlers.pointerup({pointerId:1});
  await new Promise(resolve=>setImmediate(resolve));
  const move=calls.find(call=>call.url.endsWith('pointer'));
  assert.deepEqual(move.payload,{dx:30,dy:15});
  const before=calls.filter(call=>call.url.endsWith('pointer')).length;
  vm.runInContext("online=false; pointerPending={dx:200,dy:200}; flushPointer(); online=true; flushPointer();",context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls.filter(call=>call.url.endsWith('pointer')).length,before,'Offline movements replayed');
  pad.handlers.pointerdown({pointerId:2,clientX:10,clientY:10,preventDefault(){}});
  pad.handlers.pointercancel();
  assert.equal(vm.runInContext('gesture',context),null);
  const previousCaptureEpoch=vm.runInContext('captureEpoch',context);
  node('capture-preview').hidden=false;
  vm.runInContext("activeTab='media'; selectTab('overview',false);",context);
  assert.equal(node('capture-preview').hidden,true,'Preview survives leaving media tab');
  assert.equal(vm.runInContext('captureEpoch',context),previousCaptureEpoch+1);
  node('capture-player').requestFullscreen=async()=>{throw new Error('Unsupported fullscreen');};
  await vm.runInContext("playerFullscreen(document.getElementById('capture-player'))",context);
  assert.equal(node('capture-player').classList.contains('expanded'),true,'Missing full-window fallback');
  await vm.runInContext("closePlayerFullscreen(document.getElementById('capture-player'))",context);
  assert.equal(node('capture-player').classList.contains('expanded'),false);
  vm.runInContext("showImage(new Blob(['fixture'],{type:'image/jpeg'}))",context);
  assert.equal(node('image-viewer').open,true);
  vm.runInContext('closeImageViewer()',context);
  assert.equal(node('image-viewer').open,false);
};

if (require.main===module) module.exports().then(()=>console.log('Touchpad gesture tests PASS')).catch(error=>{console.error(error);process.exitCode=1;});
