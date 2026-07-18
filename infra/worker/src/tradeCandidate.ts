export interface OpenTradeCandidate {
  id: string | number;
  execution_mode?: string | null;
  strategy_variant?: string | null;
}

/**
 * Select one open trade without crossing explicit strategy or execution scope.
 *
 * Null metadata is treated as legacy/unknown. Explicitly conflicting metadata
 * is never accepted, even when it is the only candidate for a position ID.
 */
export function chooseOpenTradeCandidate(
  candidates: OpenTradeCandidate[],
  executionMode: string | null,
  strategyVariant: string | null,
): OpenTradeCandidate | null {
  if (candidates.length === 0) return null;

  const exact = candidates.filter((candidate) => {
    const modeMatches = !executionMode || candidate.execution_mode === executionMode;
    const variantMatches = !strategyVariant || candidate.strategy_variant === strategyVariant;
    return modeMatches && variantMatches;
  });

  if (exact.length === 1) return exact[0];
  if (exact.length > 1) {
    throw new Error("Ambiguous open-trade link: multiple exact candidates");
  }

  if (candidates.length === 1) {
    const candidate = candidates[0];
    const modeMismatch = Boolean(
      executionMode &&
        candidate.execution_mode &&
        candidate.execution_mode !== executionMode,
    );
    const variantMismatch = Boolean(
      strategyVariant &&
        candidate.strategy_variant &&
        candidate.strategy_variant !== strategyVariant,
    );
    if (modeMismatch || variantMismatch) return null;
    return candidate;
  }

  const compatibleLegacy = candidates.filter((candidate) => {
    const modeCompatible =
      !executionMode ||
      !candidate.execution_mode ||
      candidate.execution_mode === executionMode;
    const variantCompatible =
      !strategyVariant ||
      !candidate.strategy_variant ||
      candidate.strategy_variant === strategyVariant;
    return modeCompatible && variantCompatible;
  });

  if (compatibleLegacy.length === 1) return compatibleLegacy[0];
  if (compatibleLegacy.length === 0) return null;
  throw new Error("Ambiguous open-trade link: multiple compatible legacy candidates");
}
