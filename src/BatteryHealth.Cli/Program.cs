using System.Globalization;
using System.Text.Json;
using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Services;
using BatteryHealth.Core.Simulation;

static int Usage()
{
    Console.WriteLine("""
        BatteryHealth CLI (cross-platform)

        Commands:
          info <battery.json|calce.csv>
          forecast <path> [--cycle N]
          simulate <path> [--temp C] [--crate C] [--cycle N] [--eol 0.7|0.8]
        """);
    return 2;
}

if (args.Length == 0)
{
    return Usage();
}

var command = args[0].ToLowerInvariant();
if (command is "-h" or "--help" or "help")
{
    return Usage();
}

if (args.Length < 2)
{
    return Usage();
}

var path = args[1];
using var service = new BatteryAnalyticsService();
var battery = service.Load(path);

switch (command)
{
    case "info":
        var discharges = battery.DischargeCycles.ToList();
        var first = discharges.FirstOrDefault()?.CapacityAh;
        var last = discharges.LastOrDefault()?.CapacityAh;
        Console.WriteLine($"{battery.BatteryId}  source={battery.Source}  cycles={discharges.Count}");
        Console.WriteLine($"rated={battery.RatedCapacityAh} Ah  EOL={battery.EolCapacityFraction:P0} ({battery.EolCapacityAh:F2} Ah)");
        Console.WriteLine($"capacity first/last = {first:F3} / {last:F3} Ah");
        return 0;

    case "forecast":
    {
        var cycle = GetInt(args, "--cycle");
        var result = service.Forecast(battery, cycle);
        Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        return 0;
    }

    case "simulate":
    {
        var scenario = new StressScenario
        {
            AmbientTemperatureC = GetDouble(args, "--temp") ?? 24,
            DischargeCRate = GetDouble(args, "--crate") ?? 1,
            CurrentCycle = GetInt(args, "--cycle"),
            EolCapacityFraction = GetDouble(args, "--eol"),
        };
        var sim = service.Simulate(battery, scenario);
        Console.WriteLine($"AF={sim.AccelerationFactor:F3}  (T={sim.TemperatureAcceleration:F3} × C={sim.CRateAcceleration:F3})");
        Console.WriteLine(DegradationSimulator.ScenarioClaim);
        Console.WriteLine($"baseline RUL={sim.BaselineRulCycles} cycles  stressed RUL={sim.StressedRulCycles} cycles");
        Console.WriteLine($"EOL cycle baseline/stressed = {sim.BaselineEolCycle} / {sim.StressedEolCycle}");
        return 0;
    }

    default:
        return Usage();
}

static int? GetInt(string[] argv, string name)
{
    var v = GetDouble(argv, name);
    return v is { } d ? (int)Math.Round(d) : null;
}

static double? GetDouble(string[] argv, string name)
{
    for (var i = 0; i < argv.Length - 1; i++)
    {
        if (string.Equals(argv[i], name, StringComparison.OrdinalIgnoreCase))
        {
            return double.Parse(argv[i + 1], CultureInfo.InvariantCulture);
        }
    }

    return null;
}
