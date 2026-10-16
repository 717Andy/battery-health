using System.Text.Json;
using BatteryHealth.App.Charts;
using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using LiveChartsCore;
using LiveChartsCore.SkiaSharpView;

namespace BatteryHealth.App.ViewModels;

public partial class ForecastViewModel : ObservableObject
{
    public WorkspaceViewModel Workspace { get; }

    [ObservableProperty] private string sohText = "—";
    [ObservableProperty] private string rul70Text = "—";
    [ObservableProperty] private string rul70FadeText = "—";
    [ObservableProperty] private string rul80Text = "—";
    [ObservableProperty] private string featureShiftText = "";
    [ObservableProperty] private string observedText = "No measured capacity on this cycle.";
    [ObservableProperty] private string typicalErrorText =
        "Typical protocol error loads from artifacts/metrics.json.";
    [ObservableProperty] private string applicabilityText = ProtocolError.Applicability;
    [ObservableProperty] private string warningText = "";
    [ObservableProperty] private string emptyHint = "Load a cell log, or open the B0005 demo.";
    [ObservableProperty] private string metricsText = "Train the Python pipeline to populate artifacts/metrics.json.";
    [ObservableProperty] private bool hasBattery;
    [ObservableProperty] private ISeries[] sohSeries = [];
    [ObservableProperty] private string headline = "Run a forecast on the loaded cell.";

    private string? _typicalError;

    public Axis[] CycleAxis { get; } = ChartFactory.CycleAxis();
    public Axis[] SohAxis { get; } = ChartFactory.SohAxis();

    public ForecastViewModel(WorkspaceViewModel workspace)
    {
        Workspace = workspace;
        workspace.BatteryChanged += (_, _) => Refresh();
        workspace.CycleChanged += (_, _) => Refresh();
        TryLoadMetrics();
        TypicalErrorText = _typicalError ?? TypicalErrorText;
    }

    [RelayCommand]
    public void Refresh()
    {
        Workspace.RefreshForecast();
        HasBattery = Workspace.Battery is not null;
        EmptyHint = HasBattery ? "" : "Load a cell log, or open the B0005 demo.";
        ApplicabilityText = ProtocolError.Applicability;
        WarningText = DescribeWarnings(Workspace.Battery, Workspace.SelectedCycle);
        var forecast = Workspace.Forecast;
        if (forecast is null)
        {
            SohText = "—";
            Rul70Text = "—";
            Rul70FadeText = "—";
            Rul80Text = "—";
            FeatureShiftText = "";
            return;
        }

        SohText = $"{forecast.PredictedSohPercent:0.0}%";
        Rul70Text = $"{forecast.PredictedRulCycles:0} cycles";
        var fade70 = Workspace.Battery is { } fadeBattery
            ? FadeRul.EstimateCycles(fadeBattery, 0.70, forecast.CycleIndex)
            : 0;
        var rul80 = Workspace.Battery is { } battery
            ? FadeRul.EstimateCycles(battery, 0.80, forecast.CycleIndex)
            : 0;
        Rul70FadeText = $"{fade70:0} cycles on the fade curve";
        Rul80Text = $"{rul80:0} cycles";
        FeatureShiftText = DescribeShift(forecast, Workspace.Trajectory?.Points);
        ObservedText = forecast.ObservedSoh is { } obs
            ? $"Measured SoH {obs * 100:0.0}% of the nameplate  ·  |error| vs model {Math.Abs(forecast.PredictedSoh - obs) * 100:0.2} points"
            : "No coulomb-counted capacity on this cycle — SoH is inferred from the V/I/T curve.";
        Headline = $"{forecast.BatteryId} cycle {forecast.CycleIndex}";
        TypicalErrorText = _typicalError ?? "Typical protocol error is unavailable until artifacts/metrics.json is loaded.";

        if (Workspace.Battery is { } rec)
        {
            var snapshot = Workspace.Trajectory;
            if (snapshot is null || !ReferenceEquals(snapshot.Battery, rec))
            {
                SohSeries = [];
                return;
            }

            if (snapshot.Error is not null)
            {
                Workspace.ErrorMessage = snapshot.Error;
                SohSeries = [];
                return;
            }

            try
            {
                SohSeries = ChartFactory.SohSeries(snapshot.Points, rec);
            }
            catch (Exception ex)
            {
                Workspace.ErrorMessage = ex.Message;
                SohSeries = [];
            }
        }
    }

    public void ExportTo(string path)
    {
        if (Workspace.Battery is null || Workspace.Trajectory is not { Points.Count: > 0, Error: null } snapshot)
        {
            Workspace.ErrorMessage = "Load a cell before exporting.";
            return;
        }

        var scenario = new StressScenario
        {
            AmbientTemperatureC = Workspace.ScenarioAmbientC,
            DischargeCRate = Workspace.ScenarioCRate,
            CurrentCycle = Workspace.SelectedCycle?.CycleIndex,
        };
        var report = Workspace.Service.BuildDecision(
            Workspace.Battery,
            snapshot.Points,
            scenario,
            _typicalError,
            Workspace.SelectedCycle?.CycleIndex);
        DecisionReport.WritePair(path, report);
        Workspace.Status = $"Wrote {Path.ChangeExtension(path, ".csv")} and {Path.ChangeExtension(path, ".json")}.";
        Workspace.ErrorMessage = null;
    }

    private static string DescribeWarnings(BatteryRecord? battery, BatteryCycle? cycle)
    {
        if (battery is null)
        {
            return "";
        }

        var warnings = new List<string>();
        if (cycle is not null && !cycle.HasTrace && cycle.Features is not { Count: > 0 })
        {
            warnings.Add("This cycle has no sensor trace and no features, so it cannot be scored.");
        }

        if (battery.RatedCapacityAssumed)
        {
            warnings.Add("Rated capacity was not in the file. The nameplate stays assumed until you set it. Measured SoH and both end-of-life lines follow that nameplate.");
        }

        if (Math.Abs(battery.RatedCapacityAh - BatteryRecord.TrainingRatedCapacityAh) > 1e-6)
        {
            warnings.Add($"{ProtocolError.ModelFitNote} Measured SoH and the end-of-life lines use {battery.RatedCapacityAh:0.00} Ah.");
        }

        return string.Join(" ", warnings);
    }

    private static string DescribeShift(ForecastResult forecast, IReadOnlyList<ForecastResult>? trajectory)
    {
        if (trajectory is not { Count: > 0 })
        {
            return "";
        }

        var baseline = trajectory
            .OrderBy(point => point.CycleIndex)
            .FirstOrDefault(point => FeatureShift.Columns.All(point.Features.ContainsKey));
        if (baseline is null || !FeatureShift.Columns.All(forecast.Features.ContainsKey))
        {
            return "";
        }

        return FeatureShift.Describe(forecast.CycleIndex, forecast.Features, baseline.CycleIndex, baseline.Features);
    }

    private void TryLoadMetrics()
    {
        foreach (var candidate in new[]
                 {
                     Path.Combine(AppContext.BaseDirectory, "Models", "metrics.json"),
                     Path.Combine(AppContext.BaseDirectory, "artifacts", "metrics.json"),
                 })
        {
            if (!File.Exists(candidate))
            {
                continue;
            }

            var json = File.ReadAllText(candidate);
            using var doc = JsonDocument.Parse(json);
            MetricsText = DescribeMetrics(doc.RootElement);
            if (ProtocolError.TryRead(json, out var rmse, out var n))
            {
                _typicalError = ProtocolError.TypicalMiss(rmse, n);
                TypicalErrorText = _typicalError;
            }

            return;
        }
    }

    internal static string DescribeMetrics(JsonElement root)
    {
        var family = "gradient boosting";
        var fitScope = "all-rows";
        var holdoutScope = "holdout-excluded";
        if (root.TryGetProperty("productionModel", out var prod))
        {
            if (prod.TryGetProperty("family", out var fam) && fam.ValueKind == JsonValueKind.String)
            {
                family = fam.GetString() ?? family;
            }
            else if (prod.TryGetProperty("type", out var type) && type.ValueKind == JsonValueKind.String)
            {
                family = type.GetString() ?? family;
            }

            if (prod.TryGetProperty("fitScope", out var scope))
            {
                fitScope = scope.GetString() ?? fitScope;
            }

            if (prod.TryGetProperty("holdoutMetricsFitScope", out var holdScope))
            {
                holdoutScope = holdScope.GetString() ?? holdoutScope;
            }
        }

        var nRows = root.TryGetProperty("nRows", out var rows) ? rows.GetInt32() : 0;
        var batteries = root.TryGetProperty("batteries", out var bats) && bats.ValueKind == JsonValueKind.Array
            ? string.Join(", ", bats.EnumerateArray().Select(b => b.GetString()))
            : "the training cells";
        var holdoutBattery = root.TryGetProperty("holdoutBattery", out var holdId)
            ? holdId.GetString() ?? "hold-out"
            : "hold-out";

        var rulText = ReadHoldout(root, "rul");
        var sohText = ReadHoldout(root, "soh");
        return
            $"Shipped ONNX ({family}) fit scope: {fitScope}" +
            (nRows > 0 ? $" ({nRows} rows, {batteries}). " : ". ") +
            $"The {holdoutBattery} numbers use fit scope {holdoutScope}, so they are not the error of the files on disk. " +
            $"RUL {rulText}. SoH {sohText}.";
    }

    private static string ReadHoldout(JsonElement root, string target)
    {
        if (root.TryGetProperty(target, out var block) &&
            block.TryGetProperty("gbr", out var gbr) &&
            gbr.TryGetProperty("holdout", out var hold))
        {
            var rmse = hold.GetProperty("rmse").GetDouble();
            var mae = hold.GetProperty("mae").GetDouble();
            var r2 = hold.GetProperty("r2").GetDouble();
            return target == "rul"
                ? $"RMSE {rmse:0.0} cycles, MAE {mae:0.0}, R² {r2:0.00}"
                : $"RMSE {rmse:0.0000} (fraction), MAE {mae:0.0000}, R² {r2:0.00}";
        }

        return "hold-out metrics unavailable";
    }
}
