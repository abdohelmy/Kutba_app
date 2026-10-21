"use client";
import {useState} from "react";
import {Button} from "@/components/ui/button";
import {Textarea} from "@/components/ui/textarea";
import {Dialog,DialogContent,DialogTitle,DialogDescription} from "@/components/ui/dialog";
import {api} from "@/lib/khutba";
export function LiveWorkerSettings({notify}:{notify:(message:string)=>void}){
 const [token,setToken]=useState(""),[busy,setBusy]=useState(false);
 return <section className="panel"><h2>Windows speech worker</h2><p>Connect the desktop to enable live imam tracking. This token only permits temporary audio transcription jobs, not account or khutba editing.</p><p><a href="/downloads/khutba-live-worker-windows.zip" download>Download Windows worker and setup guide</a></p><div className="actions"><Button disabled={busy} onClick={async()=>{setBusy(true);try{const result=await api<{token:string}>("owner/live-worker-token","POST");setToken(result.token);}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}>Issue worker token</Button><Button variant="outline" disabled={busy} onClick={async()=>{setBusy(true);try{await api("owner/live-worker-token","DELETE");notify("Speech worker disconnected and token revoked.");}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}>Disconnect worker</Button></div><Dialog open={!!token} onOpenChange={open=>{if(!open)setToken("");}}><DialogContent><DialogTitle>Speech-worker token</DialogTitle><DialogDescription>Paste this privately into the Windows worker. Valid for 30 days. Issuing a new token disconnects the previous worker.</DialogDescription><Textarea aria-label="Speech worker token" readOnly value={token}/><Button onClick={async()=>{try{await navigator.clipboard.writeText(token);notify("Token copied.");}catch{notify("Select and copy the token above.");}}}>Copy token</Button></DialogContent></Dialog></section>;
}
