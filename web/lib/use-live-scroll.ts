"use client";
import {useEffect, useRef, type RefObject} from "react";

// Keep a sentence in a reading band; moving every time a word changes is tiring.
export function useLiveScroll(
  article: RefObject<HTMLElement | null>, signature: string, enabled: boolean,
  blocked: boolean, onPause: () => void, textSize: number,
) {
  const frame = useRef(0);
  const pause = useRef(onPause);
  pause.current = onPause;
  useEffect(() => {
    if (!enabled) return;
    const cancel = () => {
      cancelAnimationFrame(frame.current);
      pause.current();
    };
    const key = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement)?.closest("input,textarea,select,[contenteditable='true'],[role='dialog']")) return;
      if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(event.key)) cancel();
    };
    window.addEventListener("wheel", cancel, {passive:true});
    window.addEventListener("touchmove", cancel, {passive:true});
    window.addEventListener("keydown", key);
    return () => {
      cancelAnimationFrame(frame.current);
      window.removeEventListener("wheel", cancel);
      window.removeEventListener("touchmove", cancel);
      window.removeEventListener("keydown", key);
    };
  }, [enabled]);

  useEffect(() => {
    cancelAnimationFrame(frame.current);
    if (!enabled || blocked) return;
    frame.current = requestAnimationFrame(() => {
      // Inline highlights can be split by Arabic terms and source icons. Use
      // the first real text line rather than the union rectangle of a long span.
      const targets = article.current?.querySelectorAll<HTMLElement>("[data-live-highlight='true']") || [];
      const rects = Array.from(targets).flatMap(target => Array.from(target.getClientRects()))
        .filter(rect => rect.width > 0 && rect.height > 0);
      const first = rects[0];
      if (!first) return;
      const viewport = window.visualViewport;
      const height = viewport?.height || window.innerHeight;
      const top = viewport?.offsetTop || 0;
      const safeTop = top + Math.max(48, height * 0.18);
      const safeBottom = top + height * 0.65;
      if (first.top >= safeTop && first.bottom <= safeBottom) return;
      const origin = window.scrollY;
      const maximum = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      const destination = Math.max(0, Math.min(maximum, origin + first.top - (top + height * 0.30)));
      const distance = destination - origin;
      if (Math.abs(distance) < 4) return;
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
        window.scrollTo({top:destination, behavior:"instant"});
        return;
      }
      const duration = Math.min(850, Math.max(380, Math.abs(distance) * 0.45));
      const started = performance.now();
      const animate = (now: number) => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = progress < 0.5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;
        window.scrollTo({top:origin + distance * eased, behavior:"instant"});
        if (progress < 1) frame.current = requestAnimationFrame(animate);
      };
      frame.current = requestAnimationFrame(animate);
    });
    return () => cancelAnimationFrame(frame.current);
  }, [article, signature, enabled, blocked, textSize]);
}
