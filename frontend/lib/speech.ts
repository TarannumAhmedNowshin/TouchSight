/** Thin wrappers over the browser's built-in speech synthesis and recognition (no API keys, no cost). */

export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

let queueToken = 0;

export function stopSpeaking() {
  queueToken++;
  if (canSpeak()) window.speechSynthesis.cancel();
}

/** Speak now, interrupting whatever was playing. */
export function speak(text: string, rate = 1): Promise<void> {
  if (!canSpeak() || !text) return Promise.resolve();
  stopSpeaking();
  return say(text, rate);
}

function say(text: string, rate: number): Promise<void> {
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = rate;
    u.lang = "en-GB";
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

/** Speak a list in order; returns false if interrupted. onStep reports which item is playing. */
export async function speakQueue(items: string[], onStep?: (i: number) => void): Promise<boolean> {
  if (!canSpeak()) return false;
  stopSpeaking();
  const token = queueToken;
  for (let i = 0; i < items.length; i++) {
    if (token !== queueToken) return false;
    onStep?.(i);
    await say(items[i], 1);
  }
  return token === queueToken;
}

// ---------------------------------------------------------------- recognition
type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};

function recognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export const canListen = () => recognitionCtor() !== null;

/** Listen for one question. Calls onInterim while speaking and onFinal with the full transcript. */
export function listen(handlers: {
  onInterim: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (message: string) => void;
  onEnd: () => void;
}): () => void {
  const Ctor = recognitionCtor();
  if (!Ctor) {
    handlers.onError("Voice input isn't available in this browser. Type your question instead.");
    handlers.onEnd();
    return () => {};
  }
  const rec = new Ctor();
  rec.lang = "en-GB";
  rec.interimResults = true;
  rec.continuous = false;
  rec.onresult = (e) => {
    let text = "";
    let final = false;
    for (let i = 0; i < e.results.length; i++) {
      text += e.results[i][0].transcript;
      final = final || e.results[i].isFinal;
    }
    if (final) handlers.onFinal(text.trim());
    else handlers.onInterim(text);
  };
  rec.onerror = (e) => {
    const messages: Record<string, string> = {
      "not-allowed": "Microphone access was blocked. Allow it in the browser, or type your question.",
      "no-speech": "I didn't hear anything. Try again, a little closer to the microphone.",
      network: "Voice recognition needs an internet connection.",
    };
    if (e.error !== "aborted") handlers.onError(messages[e.error] || "Voice input stopped. Try again or type your question.");
  };
  rec.onend = handlers.onEnd;
  stopSpeaking(); // don't transcribe our own voice
  rec.start();
  return () => rec.abort();
}
