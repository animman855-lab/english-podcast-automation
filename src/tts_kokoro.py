from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline


class KokoroTTS:
    def __init__(self, lang_code: str = "a", sample_rate: int = 24000) -> None:
        self.sample_rate = sample_rate
        self.pipeline = KPipeline(lang_code=lang_code)

    def synthesize_to_file(self, text: str, voice: str, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        chunks: list[np.ndarray] = []
        generator = self.pipeline(text, voice=voice)
        for _, _, audio in generator:
            chunks.append(np.asarray(audio, dtype=np.float32))

        if not chunks:
            raise RuntimeError("Kokoro returned no audio chunks.")

        combined = np.concatenate(chunks)
        sf.write(output, combined, self.sample_rate)
        return output
