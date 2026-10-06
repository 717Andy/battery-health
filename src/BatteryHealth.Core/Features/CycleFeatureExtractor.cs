namespace BatteryHealth.Core.Features;

/// <summary>
/// Per-cycle time-series features. Column order must match
/// <c>artifacts/models/feature_spec.json</c> and the Python extractor.
/// </summary>
public static class CycleFeatureExtractor
{
    public static readonly string[] SohColumns =
    [
        "cycle_index",
        "voltage_mean",
        "voltage_std",
        "voltage_min",
        "voltage_max",
        "voltage_start",
        "voltage_end",
        "voltage_slope",
        "current_mean",
        "current_std",
        "temp_mean",
        "temp_std",
        "temp_max",
        "temp_rise",
        "duration_s",
        "energy_wh",
        "time_to_3v5",
        "time_to_3v0",
        "ambient_temp_c",
    ];

    public static readonly string[] RulColumns = [.. SohColumns, "soh"];

    public static Dictionary<string, double> Extract(
        int cycleIndex,
        IReadOnlyList<double> timeS,
        IReadOnlyList<double> voltageV,
        IReadOnlyList<double> currentA,
        IReadOnlyList<double> temperatureC,
        double ambientTempC = 24.0,
        double? soh = null)
    {
        var n = new[] { timeS.Count, voltageV.Count, currentA.Count > 0 ? currentA.Count : timeS.Count, temperatureC.Count > 0 ? temperatureC.Count : timeS.Count }.Min();
        var t = Take(timeS, n);
        var v = Take(voltageV, n);
        var i = currentA.Count > 0 ? Take(currentA, n) : new double[n];
        var temp = temperatureC.Count > 0 ? Take(temperatureC, n) : Enumerable.Repeat(ambientTempC, n).ToArray();

        var duration = n >= 2 ? t[^1] - t[0] : 0.0;
        var power = new double[n];
        for (var k = 0; k < n; k++)
        {
            power[k] = v[k] * Math.Abs(i[k]);
        }

        var energyWh = n >= 2 ? Trapezoid(power, t) / 3600.0 : 0.0;
        var features = new Dictionary<string, double>(StringComparer.Ordinal)
        {
            ["cycle_index"] = cycleIndex,
            ["voltage_mean"] = Mean(v),
            ["voltage_std"] = Std(v),
            ["voltage_min"] = n > 0 ? v.Min() : 0,
            ["voltage_max"] = n > 0 ? v.Max() : 0,
            ["voltage_start"] = n > 0 ? v[0] : 0,
            ["voltage_end"] = n > 0 ? v[^1] : 0,
            ["voltage_slope"] = Slope(t, v),
            ["current_mean"] = Mean(i),
            ["current_std"] = Std(i),
            ["temp_mean"] = n > 0 ? Mean(temp) : ambientTempC,
            ["temp_std"] = Std(temp),
            ["temp_max"] = n > 0 ? temp.Max() : ambientTempC,
            ["temp_rise"] = n > 0 ? temp.Max() - temp.Min() : 0,
            ["duration_s"] = duration,
            ["energy_wh"] = energyWh,
            ["time_to_3v5"] = TimeToVoltage(t, v, 3.5),
            ["time_to_3v0"] = TimeToVoltage(t, v, 3.0),
            ["ambient_temp_c"] = ambientTempC,
        };
        if (soh.HasValue)
        {
            features["soh"] = soh.Value;
        }

        return features;
    }

    public static Dictionary<string, double> Extract(BatteryHealth.Core.Domain.BatteryCycle cycle, double? soh = null) =>
        Extract(
            cycle.CycleIndex,
            cycle.TimeS,
            cycle.VoltageV,
            cycle.CurrentA,
            cycle.TemperatureC,
            cycle.AmbientTemperatureC ?? 24.0,
            soh);

    public static float[] Vector(IReadOnlyDictionary<string, double> features, IReadOnlyList<string> columns)
    {
        var vec = new float[columns.Count];
        for (var i = 0; i < columns.Count; i++)
        {
            vec[i] = features.TryGetValue(columns[i], out var value) ? (float)value : 0f;
        }

        return vec;
    }

    internal static double TimeToVoltage(IReadOnlyList<double> timeS, IReadOnlyList<double> voltage, double threshold)
    {
        if (timeS.Count == 0 || voltage.Count == 0)
        {
            return 0;
        }

        var n = Math.Min(timeS.Count, voltage.Count);
        for (var i = 0; i < n; i++)
        {
            if (voltage[i] > threshold)
            {
                continue;
            }

            if (i == 0)
            {
                return timeS[0];
            }

            var v0 = voltage[i - 1];
            var v1 = voltage[i];
            var t0 = timeS[i - 1];
            var t1 = timeS[i];
            if (Math.Abs(v1 - v0) < 1e-12)
            {
                return t1;
            }

            var frac = (threshold - v0) / (v1 - v0);
            return t0 + frac * (t1 - t0);
        }

        return timeS[n - 1];
    }

    private static double[] Take(IReadOnlyList<double> src, int n)
    {
        var dst = new double[n];
        for (var i = 0; i < n; i++)
        {
            dst[i] = src[i];
        }

        return dst;
    }

    private static double Mean(IReadOnlyList<double> x) => x.Count == 0 ? 0 : x.Average();

    private static double Std(IReadOnlyList<double> x)
    {
        if (x.Count == 0)
        {
            return 0;
        }

        var mean = Mean(x);
        var acc = 0.0;
        foreach (var v in x)
        {
            var d = v - mean;
            acc += d * d;
        }

        return Math.Sqrt(acc / x.Count);
    }

    private static double Slope(IReadOnlyList<double> x, IReadOnlyList<double> y)
    {
        var n = Math.Min(x.Count, y.Count);
        if (n < 2)
        {
            return 0;
        }

        var mx = 0.0;
        var my = 0.0;
        for (var i = 0; i < n; i++)
        {
            mx += x[i];
            my += y[i];
        }

        mx /= n;
        my /= n;
        var num = 0.0;
        var den = 0.0;
        for (var i = 0; i < n; i++)
        {
            var dx = x[i] - mx;
            num += dx * (y[i] - my);
            den += dx * dx;
        }

        return Math.Abs(den) < 1e-18 ? 0 : num / den;
    }

    private static double Trapezoid(IReadOnlyList<double> y, IReadOnlyList<double> x)
    {
        var s = 0.0;
        var n = Math.Min(x.Count, y.Count);
        for (var i = 1; i < n; i++)
        {
            s += 0.5 * (y[i] + y[i - 1]) * (x[i] - x[i - 1]);
        }

        return s;
    }
}
