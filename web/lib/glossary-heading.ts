import type {Term} from './khutba';

export function glossaryHeading(text:string, term:Term, language='en'):string {
  const start=term.translation_start;
  const neutral=language==='da'?'Ordforklaring':'Word meaning';
  if(start===undefined) return neutral;
  const preceding=Array.from(text).slice(0,start).join('').replace(/[(（]\s*$/u,'').trimEnd();
  const candidates=[
    ...(!term.popup_language || term.popup_language===language ? [term.popup_phrase] : []),
    language==='da'?term.localized_phrase:term.english_phrase,
  ];
  for(const candidate of candidates) {
    if(!candidate?.trim()) continue;
    const escaped=candidate.trim().split(/\s+/u).map(word=>word.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('\\s+');
    const match=preceding.match(new RegExp(`(?<![\\p{L}\\p{N}_])${escaped}\\s*$`,'iu'));
    if(match) return match[0].trimEnd();
  }
  return preceding.split(/[\r\n.!?;:…,)]+/u).at(-1)?.trim().replace(/^[‘’"“”]+/u,'') || neutral;
}
