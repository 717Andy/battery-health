using System.Globalization;
using System.Text.Json;
using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Inference;
using BatteryHealth.Core.Services;
using BatteryHealth.Core.Simulation;

static int Usage()
{
    Console.WriteLine("""
        BatteryHealth CLI (cross-platform)

        Commands:
          info <battery.json|calce.csv>
          forecast <path> [--cycle N] [--rated Ah]
          simulate <path> [--temp C] [--crate C] [--cycle N] [--eol 0.7|0.8] [--rated Ah]
          export <path> --out <report.csv|report.json> [--temp C] [--crate C] [--cycle N] [--rated Ah]
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
if (GetDouble(args, "--rated") is { } ratedAh)
{
    if (ratedAh <= 0)
    {
        Console.Error.WriteLine("Rated capacity must be positive.");
        return 2;
    }

    battery.RatedCapacityAh = ratedAh;
    battery.RatedCapacityAssumed = false;
}

switch (command)
{
    case "info":
        var discharges = battery.DischargeCycles.ToList();
        var first = discharges.FirstOrDefault()?.CapacityAh;
        var last = discharges.LastOrDefault()?.CapacityAh;
        Console.WriteLine($"{battery.BatteryId}");
        foreach (var line in IntakeReport.From(battery).Lines)
        {
            Console.WriteLine(line);
        }

        Console.WriteLine($"capacity first/last = {first:F3} / {last:F3} Ah");
        return 0;

    case "forecast":
    {
        var cycle = GetInt(args, "--cycle");
        try
        {
            var result = service.Forecast(battery, cycle);
            Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }
        catch (InvalidOperationException ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 2;
        }
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

    case "export":
    {
        var outPath = GetString(args, "--out");
        if (string.IsNullOrWhiteSpace(outPath))
        {
            Console.Error.WriteLine("export requires --out <report.csv|report.json>.");
            return 2;
        }

        var scenario = new StressScenario
        {
            AmbientTemperatureC = GetDouble(args, "--temp") ?? 24,
            DischargeCRate = GetDouble(args, "--crate") ?? 1,
            CurrentCycle = GetInt(args, "--cycle"),
            EolCapacityFraction = GetDouble(args, "--eol"),
        };
        var trajectory = service.ForecastTrajectory(battery);
        string? typical = null;
        var modelDir = ModelLocator.FindDirectory();
        var metricsPath = modelDir is null
            ? null
            : Path.GetFullPath(Path.Combine(modelDir, "..", "metrics.json"));
        if (metricsPath is not null && File.Exists(metricsPath) &&
            ProtocolError.TryRead(File.ReadAllText(metricsPath), out var rmse, out var n))
        {
            typical = ProtocolError.TypicalMiss(rmse, n);
        }

        DecisionReport report;
        try
        {
            report = service.BuildDecision(battery, trajectory, scenario, typical, scenario.CurrentCycle);
        }
        catch (InvalidOperationException ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 2;
        }

        DecisionReport.WritePair(outPath, report);
        var csvPath = Path.ChangeExtension(outPath, ".csv");
        var jsonPath = Path.ChangeExtension(outPath, ".json");
        Console.WriteLine($"Wrote {csvPath}");
        Console.WriteLine($"Wrote {jsonPath}");
        return 0;
    }

    default:
        return Usage();
}

static string? GetString(string[] argv, string name)
{
    for (var i = 0; i < argv.Length - 1; i++)
    {
        if (string.Equals(argv[i], name, StringComparison.OrdinalIgnoreCase))
        {
            return argv[i + 1];
        }
    }

    return null;
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
