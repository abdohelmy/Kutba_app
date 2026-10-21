// Microphone-only PCM buffering. No recording is written to browser storage.
class KhutbaAudio extends AudioWorkletProcessor {
  constructor() { super(); this.buffers=[]; this.length=0; this.levelFrames=0; this.levelSquares=0; }
  process(inputs) {
    const input=inputs[0]?.[0];
    this.levelFrames+=input?.length||128;
    if(input)for(const sample of input)this.levelSquares+=sample*sample;
    if(this.levelFrames>=sampleRate/10){
      this.port.postMessage({type:"level",rms:Math.sqrt(this.levelSquares/this.levelFrames)});
      this.levelFrames=0;this.levelSquares=0;
    }
    if(input){this.buffers.push(new Float32Array(input));this.length+=input.length;}
    if(this.length>=sampleRate*2){
      const block=new Float32Array(this.length);let offset=0;
      for(const buffer of this.buffers){block.set(buffer,offset);offset+=buffer.length;}
      this.port.postMessage(block,[block.buffer]);this.buffers=[];this.length=0;
    }
    return true;
  }
}
registerProcessor("khutba-audio",KhutbaAudio);
