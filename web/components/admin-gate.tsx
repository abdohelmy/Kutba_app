"use client";
import {useEffect,useState} from "react";
import {api,ApiError} from "@/lib/khutba";
import {Button} from "@/components/ui/button";
export function AdminGate({children}:{children:React.ReactNode}){
 const [state,setState]=useState("Checking your sign-in…");
 const [owner,setOwner]=useState(false);
 async function check(){setState("Checking your sign-in…");try{const user=await api<{role:string}>("auth/me");setOwner(user.role==="SUPER_ADMIN");if(user.role==="SUPER_ADMIN"&&location.hash==="#admin"){location.hash="owner";return;}setState("ready");}catch(e){setState(e instanceof ApiError&&e.status===401?"Please sign in to your mosque.":(e as Error).message);}}
 useEffect(()=>{void check();},[]);
 if(state==="ready")return <>{owner&&<div className="actions"><Button variant="outline" onClick={()=>location.hash="owner"}>Owner dashboard</Button></div>}{children}</>;
 return <section className="empty"><p role="status">{state}</p><div className="actions"><Button onClick={()=>location.hash="login"}>Mosque sign in</Button><Button variant="outline" onClick={check}>Try again</Button></div></section>;
}
