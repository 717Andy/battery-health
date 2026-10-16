using BatteryHealth.Core.Domain;

namespace BatteryHealth.Core.Simulation;

/// <summary>
/// Semi-empirical thermal + C-rate stress model (mirrors <c>ml/batteryhealth/simulate.py</c>).
/// Temperature uses Arrhenius with Ea = 0.50 eV vs the NASA 24 °C reference.
/// Load uses a Wöhler power law (C / 1C)^0.60.
/// </summary>
public static class DegradationSimulator
{
    public const double ArrheniusEaEv = 0.50;
    public const double BoltzmannEvPerK = 8.617333262145e-5;
    public const double RefTemperatureC = 24.0;
    public const double RefCRate = 1.0;
    public const double CRateExponent = 0.60;

    /// <summary>
    /// Ea and the C-rate exponent are scenario constants, not a fit to the NASA cells.
    /// </summary>
    public const string ScenarioClaim =
        "Scenario acceleration referenced to 24 °C and 1C. Ea = 0.50 eV and the C-rate exponent 0.60 were not identified on the NASA cells.";

    public static double Kelvin(double tempC) => tempC + 273.15;

    public static double TemperatureAcceleration(double ambientC, double refC = RefTemperatureC, double eaEv = ArrheniusEaEv)
    {
        var t = Kelvin(ambientC);
        var tRef = Kelvin(refC);
        if (t <= 0 || tRef <= 0)
        {
            return 1;
        }

        return Math.Exp(eaEv / BoltzmannEvPerK * (1.0 / tRef - 1.0 / t));
    }

    public static double CRateAcceleration(double cRate, double refCRate = RefCRate, double exponent = CRateExponent)
    {
        cRate = Math.Max(cRate, 1e-3);
        refCRate = Math.Max(refCRate, 1e-3);
        return Math.Pow(cRate / refCRate, exponent);
    }

    public static double CombinedAcceleration(double ambientC, double cRate) =>
        ScenarioAcceleration(ambientC, cRate, ArrheniusEaEv);

    public static double ScenarioAcceleration(double ambientC, double cRate, double eaEv) =>
        TemperatureAcceleration(ambientC, eaEv: eaEv) * CRateAcceleration(cRate);

    public static StressSimulation Simulate(BatteryRecord battery, StressScenario scenario)
    {
        var rated = battery.RatedCapacityAh;
        var frac = scenario.EolCapacityFraction ?? battery.EolCapacityFraction;
        var threshold = rated * frac;
        var discharges = battery.DischargeCycles.Where(c => c.CapacityAh.HasValue).ToList();
        if (discharges.Count == 0)
        {
            throw new InvalidOperationException("Battery record has no discharge capacities");
        }

        var afT = TemperatureAcceleration(scenario.AmbientTemperatureC);
        var afC = CRateAcceleration(scenario.DischargeCRate);
        var af = afT * afC;

        var target = scenario.CurrentCycle ?? discharges[0].CycleIndex;
        var cursor = 0;
        for (var i = 0; i < discharges.Count; i++)
        {
            if (discharges[i].CycleIndex <= target)
            {
                cursor = i;
            }
        }

        var n0 = discharges[cursor].CycleIndex;
        var c0 = discharges[cursor].CapacityAh!.Value;

        var baseline = discharges.Select(c => new FadePoint
        {
            CycleIndex = c.CycleIndex,
            CapacityAh = c.CapacityAh!.Value,
            Soh = c.CapacityAh.Value / rated,
        }).ToList();

        var stressed = new List<FadePoint>(baseline.Count);
        foreach (var p in baseline)
        {
            var cap = p.CycleIndex <= n0 ? p.CapacityAh : Math.Max(0, c0 - af * (c0 - p.CapacityAh));
            stressed.Add(new FadePoint { CycleIndex = p.CycleIndex, CapacityAh = cap, Soh = cap / rated });
        }

        var (baseEol, baseEx) = FindEol(baseline, n0, threshold);
        var (stressEol, stressEx) = FindEol(stressed, n0, threshold);

        return new StressSimulation
        {
            AccelerationFactor = af,
            TemperatureAcceleration = afT,
            CRateAcceleration = afC,
            AmbientTemperatureC = scenario.AmbientTemperatureC,
            DischargeCRate = scenario.DischargeCRate,
            CurrentCycle = n0,
            CurrentCapacityAh = c0,
            EolCapacityAh = threshold,
            EolFraction = frac,
            BaselineEolCycle = baseEol,
            StressedEolCycle = stressEol,
            BaselineRulCycles = Math.Max(0, baseEol - n0),
            StressedRulCycles = Math.Max(0, stressEol - n0),
            BaselineExtrapolated = baseEx,
            StressedExtrapolated = stressEx,
            Baseline = baseline,
            Stressed = stressed,
        };
    }

    private static (int EolCycle, bool Extrapolated) FindEol(IReadOnlyList<FadePoint> points, int n0, double threshold)
    {
        foreach (var p in points)
        {
            if (p.CycleIndex >= n0 && p.CapacityAh <= threshold)
            {
                return (p.CycleIndex, false);
            }
        }

        var tail = points.Where(p => p.CycleIndex >= n0).ToList();
        if (tail.Count < 2)
        {
            tail = points.ToList();
        }

        if (tail.Count < 2)
        {
            return (points[^1].CycleIndex, true);
        }

        var dn = tail[^1].CycleIndex - tail[0].CycleIndex;
        var dc = tail[0].CapacityAh - tail[^1].CapacityAh;
        if (dn <= 0 || dc <= 1e-9)
        {
            return (points[^1].CycleIndex, true);
        }

        var rate = dc / dn;
        var remaining = tail[^1].CapacityAh - threshold;
        var extra = Math.Max(0, remaining / rate);
        return ((int)Math.Round(tail[^1].CycleIndex + extra), true);
    }
}
