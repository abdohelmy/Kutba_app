import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

let Processor;
const messages=[];
const context={sampleRate:16000,Float32Array,Math,AudioWorkletProcessor:class{
 constructor(){this.port={postMessage:message=>messages.push(message)};}
},registerProcessor:(_,value)=>{Processor=value;}};
vm.runInNewContext(readFileSync(new URL("../public/live-audio-worklet.js",import.meta.url),"utf8"),context);
const recorder=new Processor();
// 250 render blocks = two seconds. Telemetry is local and audio is unchanged.
for(let i=0;i<250;i++)assert.equal(recorder.process([[new Float32Array(128).fill(0.1)]]),true);
const levels=messages.filter(m=>m.type==="level");
assert.ok(levels.length>=18);
assert.ok(levels.every(m=>Math.abs(m.rms-0.1)<1e-6));
const chunks=messages.filter(m=>m instanceof Float32Array);
assert.equal(chunks.length,1);
assert.equal(chunks[0].length,32000);
assert.equal(chunks[0][0],new Float32Array([0.1])[0]);
for(let i=0;i<26;i++)recorder.process([[new Float32Array(128)]]);
assert.equal(messages.at(-1).rms,0);
console.log("Worklet passed: audible input, silence, intact two-second audio chunks");
