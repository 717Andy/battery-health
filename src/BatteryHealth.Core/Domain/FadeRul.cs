namespace BatteryHealth.Core.Domain;

/// <summary>
/// Cycles remaining until measured capacity crosses a fraction of the current nameplate.
/// This is the fade-curve estimate. It is not the ONNX RUL head.
/// </summary>
public static class FadeRul
{
    public static double EstimateCycles(BatteryRecord battery, double fraction, int currentCycle)
    {
        var threshold = battery.RatedCapacityAh * fraction;
        var points = battery.DischargeCycles.Where(c => c.CapacityAh.HasValue).ToList();
        foreach (var cycle in points)
        {
            if (cycle.CycleIndex >= currentCycle && cycle.CapacityAh <= threshold)
            {
                return Math.Max(0, cycle.CycleIndex - currentCycle);
            }
        }

        var tail = points.Where(c => c.CycleIndex >= currentCycle).ToList();
        if (tail.Count < 2)
        {
            return 0;
        }

        var last = tail[^1];
        var first = tail[0];
        var dn = last.CycleIndex - first.CycleIndex;
        var dc = first.CapacityAh!.Value - last.CapacityAh!.Value;
        if (dn <= 0 || dc <= 1e-9)
        {
            return 0;
        }

        var extra = Math.Max(0, (last.CapacityAh.Value - threshold) / (dc / dn));
        return Math.Max(0, last.CycleIndex + extra - currentCycle);
    }
}
