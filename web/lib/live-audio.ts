export function pcmWav(samples:Float32Array,rate:number):Blob{
 const size=Math.floor(samples.length*16000/rate),buffer=new ArrayBuffer(44+size*2),view=new DataView(buffer);
 const text=(offset:number,value:string)=>{for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i));};
 text(0,"RIFF");view.setUint32(4,36+size*2,true);text(8,"WAVE");text(12,"fmt ");view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);text(36,"data");view.setUint32(40,size*2,true);
 for(let i=0;i<size;i++){const position=i*rate/16000,index=Math.floor(position),fraction=position-index;
  const sample=(samples[index]||0)*(1-fraction)+(samples[index+1]??samples[index]??0)*fraction;
  view.setInt16(44+i*2,Math.round(Math.max(-1,Math.min(1,sample))*32767),true);
 }
 return new Blob([buffer],{type:"audio/wav"});
}

export class LiveMicrophone {
 private stream?:MediaStream;private context?:AudioContext;private node?:AudioWorkletNode;
 private previous:Float32Array=new Float32Array();private sequence=0;private blocks=0;private sending=false;private stopped=false;
 constructor(private onChunk:(blob:Blob,sequence:number,kind:"full"|"quick")=>Promise<void>,private onError:(message:string)=>void,private onLevel:(rms:number)=>void=()=>{}){}
 setNextSequence(sequence:number){this.sequence=sequence;}
 async start(){
  try{
   this.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:false,noiseSuppression:true,autoGainControl:true}});
   if(this.stopped){this.stream.getTracks().forEach(t=>t.stop());return;}
   this.context=new AudioContext();await this.context.resume();
   await this.context.audioWorklet.addModule("/live-audio-worklet.js?v=2s");
   if(this.stopped){await this.stop();return;}
   this.node=new AudioWorkletNode(this.context,"khutba-audio");
   const source=this.context.createMediaStreamSource(this.stream),silent=this.context.createGain();silent.gain.value=0;
   source.connect(this.node);this.node.connect(silent);silent.connect(this.context.destination);
   this.stream.getTracks().forEach(t=>t.addEventListener("ended",()=>{if(!this.stopped)this.onError("Microphone disconnected. Restart recording.");}));
   this.context.onstatechange=()=>{if(!this.stopped&&this.context?.state==="suspended")this.onError("Microphone paused by the browser. Keep this page open and the screen unlocked.");};
   this.node.port.onmessage=event=>{
    if(this.stopped||!this.context)return;
    if(event.data?.type==="level"){
     const rms=Number(event.data.rms);
     if(Number.isFinite(rms))this.onLevel(Math.max(0,Math.min(1,rms)));
     return;
    }
    const block=event.data as Float32Array,kind=++this.blocks%4===0?"full":"quick";
    const buffered=new Float32Array(this.previous.length+block.length);
    buffered.set(this.previous);buffered.set(block,this.previous.length);
    const joined=buffered.slice(-(kind==="full"?8:4)*this.context.sampleRate);
    this.previous=buffered.slice(-6*this.context.sampleRate);
    const sequence=this.sequence++;
    if(this.sending)return; // Drop backlog rather than publish obsolete positions.
    this.sending=true;
    void this.onChunk(pcmWav(joined,this.context.sampleRate),sequence,kind).catch(e=>{if(!this.stopped)this.onError((e as Error).message);}).finally(()=>{this.sending=false;});
   };
  }catch(e){await this.stop();throw e;}
 }
 async stop(){this.stopped=true;this.onLevel(0);this.previous=new Float32Array();this.node?.disconnect();this.node=undefined;
  this.stream?.getTracks().forEach(t=>t.stop());this.stream=undefined;
  if(this.context&&this.context.state!=="closed")await this.context.close();this.context=undefined;
 }
}
