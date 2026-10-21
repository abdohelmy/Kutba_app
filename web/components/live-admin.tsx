"use client";
import {useEffect,useRef,useState} from "react";
import {Button} from "@/components/ui/button";
import {api} from "@/lib/khutba";
import {LiveMicrophone} from "@/lib/live-audio";
import {LiveState,liveStatus} from "@/lib/live";

export function LiveAdmin({id,notify}:{id:string;notify:(s:string)=>void}){
 const [state,setState]=useState<LiveState>(),[busy,setBusy]=useState(false),[recording,setRecording]=useState(false);
 const [inputRms,setInputRms]=useState(0),[soundDetected,setSoundDetected]=useState(false);
 const lastSound=useRef(0);
 const inputLevel=Math.max(0,Math.min(100,(20*Math.log10(Math.max(inputRms,0.000001))+60)/60*100));
 const recorder=useRef<LiveMicrophone|null>(null),owned=useRef<string|undefined>(undefined),mounted=useRef(true),operating=useRef(false),wake=useRef<WakeLockSentinel|null>(null);
 async function refresh(){const query=owned.current?"?session_id="+encodeURIComponent(owned.current):"";const result=await api<LiveState>(`admin/sermons/${id}/live${query}`);if(mounted.current)setState(result);return result;}
 useEffect(()=>{mounted.current=true;let timer:ReturnType<typeof setTimeout>;let stopped=false;
  const poll=async()=>{try{const current=await refresh();if(owned.current&&!operating.current&&(!current.active||current.session_id!==owned.current||!current.worker_ready||(current.status==="paused"&&recorder.current))){await stopAudio();if(current.active&&current.session_id===owned.current&&!current.worker_ready){await api(`admin/sermons/${id}/live`,"POST",{action:"pause",session_id:owned.current});await refresh();}if(!current.active||current.session_id!==owned.current)owned.current=undefined;}}catch{}finally{if(!stopped)timer=setTimeout(poll,2500);}};
  void poll();return()=>{stopped=true;mounted.current=false;clearTimeout(timer);void recorder.current?.stop();void wake.current?.release();if(owned.current)void api(`admin/sermons/${id}/live`,"POST",{action:"stop",session_id:owned.current}).catch(()=>{});};
 },[id]);
 async function run(task:()=>Promise<void>){setBusy(true);operating.current=true;try{await task();}catch(e){notify((e as Error).name==="NotAllowedError"?"Allow microphone access to start live tracking.":(e as Error).message);}finally{operating.current=false;if(mounted.current)setBusy(false);}}
 async function stopAudio(){await recorder.current?.stop();recorder.current=null;setRecording(false);setInputRms(0);setSoundDetected(false);lastSound.current=0;await wake.current?.release();wake.current=null;}
 async function start(){
  let started:LiveState|undefined;
  const microphone=new LiveMicrophone(async(blob,sequence,kind)=>{
   if(!owned.current)return;const data=new FormData();data.append("file",blob,"speech.wav");
   await api(`admin/sermons/${id}/live/audio?session_id=${encodeURIComponent(owned.current)}&sequence=${sequence}&kind=${kind}`,"POST",data);
  },message=>{notify(message);void stopAudio();if(owned.current)void api(`admin/sermons/${id}/live`,"POST",{action:"pause",session_id:owned.current}).then(refresh).catch(()=>{});},rms=>{
   if(!mounted.current)return;
   setInputRms(rms);if(rms>=0.004)lastSound.current=Date.now();
   setSoundDetected(lastSound.current>0&&Date.now()-lastSound.current<1500);
  });
  recorder.current=microphone;
  try{
   // Request mic on the admin's explicit gesture, before a server session exists.
   await microphone.start();if(!mounted.current){await microphone.stop();return;}
   started=await api<LiveState>(`admin/sermons/${id}/live`,"POST",{action:state?.active?"resume":"start",session_id:state?.session_id});
   if(!mounted.current){await microphone.stop();await api(`admin/sermons/${id}/live`,"POST",{action:"stop",session_id:started.session_id}).catch(()=>{});return;}
   owned.current=started.session_id;setState(started);setRecording(true);
   microphone.setNextSequence((started.audio_sequence??-1)+1);
   if("wakeLock" in navigator)try{wake.current=await navigator.wakeLock.request("screen");}catch{}
  }catch(e){await stopAudio();if(started?.session_id)await api(`admin/sermons/${id}/live`,"POST",{action:"stop",session_id:started.session_id}).catch(()=>{});throw e;}
 }
 return <section className="panel live-admin"><h2>Follow the imam live</h2><p>Microphone audio is temporarily processed on the connected Windows desktop. It is not saved as a recording. Keep this page open and your screen unlocked.</p><p role="status">{recording?"Microphone on · ":""}{state?.active?liveStatus(state):state?.worker_ready?"Speech worker connected":"Speech worker offline"}</p>{recording&&<div className="live-mic-level"><div className="live-mic-label"><span>Microphone input</span><span role="status">{soundDetected?"Sound detected":"No sound detected"}</span></div><meter aria-label="Microphone input level" min={0} max={100} value={inputLevel}/>{!soundDetected&&<small>Speak near the microphone. If the bar stays empty, check your browser’s selected microphone.</small>}</div>}{state?.preparation_error&&<p className="notice">{state.preparation_error}</p>}<div className="actions">
  {!recording&&!state?.mapping_ready&&state?.preparation_error&&<Button variant="outline" disabled={busy||state?.preparing||state?.active} onClick={()=>run(async()=>{await api(`admin/sermons/${id}/live/prepare`,"POST");await refresh();})}>Retry live highlighting</Button>}
  {!recording&&<Button disabled={busy||!state?.worker_ready||!state?.mapping_ready||(state?.active&&state.status!=="paused")} onClick={()=>run(start)}>{state?.active?"Resume microphone":"Start microphone"}</Button>}
  {recording&&<Button variant="outline" disabled={busy} onClick={()=>run(async()=>{await stopAudio();await api(`admin/sermons/${id}/live`,"POST",{action:"pause",session_id:owned.current});await refresh();})}>Pause microphone</Button>}
  {state?.active&&<Button variant="outline" disabled={busy} onClick={()=>run(async()=>{await stopAudio();await api(`admin/sermons/${id}/live`,"POST",{action:"stop",session_id:state.session_id});owned.current=undefined;await refresh();})}>End live session</Button>}
 </div>{state?.preparing&&!state.mapping_ready&&<small role="status">Preparing live highlighting automatically… You can keep reading.</small>}{state?.mapping_ready&&<small>Ready to follow the imam. Position is approximate and may pause during off-script speech.</small>}</section>;
}
