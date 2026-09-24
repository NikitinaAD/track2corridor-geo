"""Create the deterministic noisy track used in the README."""

from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    output = Path(__file__).with_name("noisy-track.csv")
    rng = np.random.default_rng(42)
    x = np.linspace(0, 120, 121)
    y = 10 * np.sin(x / 22) + rng.normal(0, 0.8, len(x))
    pd.DataFrame({"x": x, "y": y, "sequence": np.arange(len(x))}).to_csv(
        output,
        index=False,
    )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
