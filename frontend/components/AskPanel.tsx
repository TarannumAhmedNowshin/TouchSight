"use client";

import { useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";
import { canListen, listen, speak } from "@/lib/speech";

type Turn = { q: string; a: string };
/** Ask the diagram: speak (or type) a question about this page and hear a grounded answer. */
export default function AskPanel({ job, partNames }: { job: string; partNames: string[] }) {
  const [first, second] = [...new Set(partNames)].slice(-2).reverse();
  const examples = [
    first && `Where is the ${first}?`,
    second && `What is next to the ${second}?`,
    "What was left out?",
  ].filter(Boolean) as string[];
  const [question, setQuestion] = useState("");
  const [listening, setListening] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [voice, setVoice] = useState(false);
  const stop = useRef<() => void>(() => {});

  useEffect(() => setVoice(canListen()), []);
  useEffect(() => { setTurns([]); setError(null); }, [job]);

  const submit = async (q: string) => {
    const text = q.trim();
    if (!text || thinking) return;
    setThinking(true);
    setError(null);
    try {
      const { answer } = await api.ask(job, text);
      setTurns((t) => [{ q: text, a: answer }, ...t].slice(0, 4));
      setQuestion("");
      speak(answer);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      speak(msg);
    } finally {
      setThinking(false);
    }
  };

  const toggleMic = () => {
    if (listening) {
      stop.current();
      setListening(false);
      return;
    }
    setError(null);
    setListening(true);
    stop.current = listen({
      onInterim: setQuestion,
      onFinal: (text) => { setQuestion(text); submit(text); },
      onError: setError,
      onEnd: () => setListening(false),
    });
  };

  return (
    <section className="ask" aria-labelledby="ask-h">
      <h2 id="ask-h">Ask the diagram</h2>
      <p className="hint">
        {voice ? "Press the microphone and ask out loud, or type." : "Type a question."} Answers are spoken and only
        use what&apos;s on this page for positions.
      </p>
      <form className="ask-row" onSubmit={(e) => { e.preventDefault(); submit(question); }}>
        {voice && (
          <button type="button" className={`mic${listening ? " on" : ""}`} onClick={toggleMic}
            aria-pressed={listening} aria-label={listening ? "Stop listening" : "Ask with your voice"}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z" /></svg>
          </button>
        )}
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={listening ? "Listening…" : examples[0]}
          aria-label="Your question"
          maxLength={300}
        />
        <button type="submit" className="btn primary" disabled={thinking || !question.trim()}>
          {thinking ? "Thinking…" : "Ask"}
        </button>
      </form>
      {turns.length === 0 && (
        <div className="examples">
          {examples.map((q) => (
            <button key={q} type="button" onClick={() => submit(q)} disabled={thinking}>{q}</button>
          ))}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <ul className="turns" aria-live="polite">
        {turns.map((t, i) => (
          <li key={i}>
            <p className="q">{t.q}</p>
            <p className="a">{t.a}</p>
            <button type="button" className="replay" onClick={() => speak(t.a)} aria-label="Play this answer again">Play again</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
