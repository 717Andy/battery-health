namespace BatteryHealth.Core.Services;

/// <summary>
/// How the selected discharge differs from the cell's first scored discharge
/// on the columns that carry the NASA constant-current result.
/// </summary>
public static class FeatureShift
{
    public static readonly string[] Columns = ["energy_wh", "duration_s", "time_to_3v0"];

    public static string Describe(
        int currentCycle,
        IReadOnlyDictionary<string, double> current,
        int baselineCycle,
        IReadOnlyDictionary<string, double> baseline)
    {
        if (currentCycle == baselineCycle)
        {
            return "This is the first scored discharge, so there is no earlier cycle to compare.";
        }

        var parts = new List<string>(Columns.Length);
        foreach (var column in Columns)
        {
            if (!current.TryGetValue(column, out var now) || !baseline.TryGetValue(column, out var then))
            {
                parts.Add($"{column} n/a");
                continue;
            }

            if (Math.Abs(then) < 1e-9)
            {
                parts.Add($"{column} n/a");
                continue;
            }

            var percent = (now - then) / Math.Abs(then) * 100.0;
            parts.Add($"{column} {percent:+0.0;-0.0;0}%");
        }

        return $"Versus the first scored discharge (cycle {baselineCycle}): {string.Join(", ", parts)}.";
    }
}
