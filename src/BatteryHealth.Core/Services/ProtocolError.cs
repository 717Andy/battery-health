using System.Text.Json;

namespace BatteryHealth.Core.Services;

/// <summary>
/// Empirical miss of the nested SoH→RUL graph on unseen NASA cells.
/// This is a protocol error, not a calibrated prediction interval.
/// </summary>
public static class ProtocolError
{
    public const string Applicability =
        "NASA constant-current 18650 discharges near 24 °C.";

    public const string ModelFitNote =
        "The SoH model is still the NASA 2.0 Ah fit. It does not take capacity as an input.";

    public static string TypicalMiss(double rmseCycles, int n) =>
        $"Typical miss on an unseen cell from this same lab protocol: {rmseCycles:0.0} cycles RMSE " +
        $"(nested SoH to RUL, censored cells excluded, n={n}). " +
        "This is an empirical error, not a calibrated prediction interval.";

    public static bool TryRead(string metricsJson, out double rmseCycles, out int n)
    {
        rmseCycles = 0;
        n = 0;
        using var doc = JsonDocument.Parse(metricsJson);
        if (!doc.RootElement.TryGetProperty("rulNestedSoh", out var nested))
        {
            return false;
        }

        if (!nested.TryGetProperty("pooledExcludingCensored", out var pooled))
        {
            return false;
        }

        rmseCycles = pooled.GetProperty("rmse").GetDouble();
        n = pooled.GetProperty("n").GetInt32();
        return true;
    }

    public static bool TryReadSohHoldoutRmse(string metricsJson, out double rmseFraction)
    {
        rmseFraction = 0;
        using var doc = JsonDocument.Parse(metricsJson);
        if (!doc.RootElement.TryGetProperty("soh", out var soh) ||
            !soh.TryGetProperty("gbr", out var gbr) ||
            !gbr.TryGetProperty("holdout", out var holdout) ||
            !holdout.TryGetProperty("rmse", out var rmse))
        {
            return false;
        }

        rmseFraction = rmse.GetDouble();
        return true;
    }
}
