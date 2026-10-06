using System.Text.Json;
using BatteryHealth.App.Charts;
using BatteryHealth.Core.Domain;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using LiveChartsCore;
using LiveChartsCore.SkiaSharpView;

namespace BatteryHealth.App.ViewModels;

public partial class ForecastViewModel : ObservableObject
{
    public WorkspaceViewModel Workspace { get; }

    [ObservableProperty] private string sohText = "—";
    [ObservableProperty] private string rulText = "—";
    [ObservableProperty] private string observedText = "No measured capacity on this cycle.";
    [ObservableProperty] private string eolText =
        "RUL is cycles until 70% of rated capacity (NASA PCoE official: 2.0 Ah → 1.4 Ah). " +
        "80% is the common EV warranty / replacement threshold.";
    [ObservableProperty] private string metricsText = "Train the Python pipeline to populate artifacts/metrics.json.";
    [ObservableProperty] private bool useOemThreshold;
    [ObservableProperty] private ISeries[] sohSeries = [];
    [ObservableProperty] private string headline = "Run a forecast on the loaded cell.";

    public Axis[] CycleAxis { get; } = ChartFactory.CycleAxis();
    public Axis[] SohAxis { get; } = ChartFactory.SohAxis();

    public ForecastViewModel(WorkspaceViewModel workspace)
    {
        Workspace = workspace;
        workspace.BatteryChanged += (_, _) => Refresh();
        workspace.CycleChanged += (_, _) => Refresh();
        TryLoadMetrics();
    }

    [RelayCommand]
    public void Refresh()
    {
        Workspace.RefreshForecast();
        var forecast = Workspace.Forecast;
        if (forecast is null)
        {
            SohText = "—";
            RulText = "—";
            return;
        }

        SohText = $"{forecast.PredictedSohPercent:0.0}%";
        var rul = forecast.PredictedRulCycles;
        if (UseOemThreshold && Workspace.Battery is { } battery)
        {
            rul = EstimateRulFromFade(battery, 0.80, forecast.CycleIndex);
            EolText = "Showing fade-curve RUL to 80% of rated capacity (OEM warranty line). The ONNX model itself is trained to the NASA 70% stop.";
        }
        else
        {
            EolText = "ONNX RUL to 70% of rated capacity (NASA PCoE official end-of-life). Toggle OEM to estimate 80% from the measured fade curve.";
        }

        RulText = $"{rul:0} cycles";
        ObservedText = forecast.ObservedSoh is { } obs
            ? $"Measured SoH {obs * 100:0.0}%  ·  |error| {Math.Abs(forecast.PredictedSoh - obs) * 100:0.2} points"
            : "No coulomb-counted capacity on this cycle — SoH is inferred from the V/I/T curve.";
        Headline = $"{forecast.BatteryId} cycle {forecast.CycleIndex}";

        if (Workspace.Battery is { } rec)
        {
            try
            {
                var traj = Workspace.Service.ForecastTrajectory(rec);
                SohSeries = ChartFactory.SohSeries(traj, rec);
            }
            catch
            {
                SohSeries = [];
            }
        }
    }

    partial void OnUseOemThresholdChanged(bool value) => Refresh();

    private static double EstimateRulFromFade(BatteryRecord battery, double fraction, int currentCycle)
    {
        var threshold = battery.RatedCapacityAh * fraction;
        var points = battery.DischargeCycles.Where(c => c.CapacityAh.HasValue).ToList();
        foreach (var c in points)
        {
            if (c.CycleIndex >= currentCycle && c.CapacityAh <= threshold)
            {
                return Math.Max(0, c.CycleIndex - currentCycle);
            }
        }

        if (points.Count < 2)
        {
            return 0;
        }

        var last = points[^1];
        var first = points.First(c => c.CycleIndex >= currentCycle);
        var dn = last.CycleIndex - first.CycleIndex;
        var dc = first.CapacityAh!.Value - last.CapacityAh!.Value;
        if (dn <= 0 || dc <= 1e-9)
        {
            return 0;
        }

        var extra = Math.Max(0, (last.CapacityAh.Value - threshold) / (dc / dn));
        return Math.Max(0, last.CycleIndex + extra - currentCycle);
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

            using var doc = JsonDocument.Parse(File.ReadAllText(candidate));
            var root = doc.RootElement;
            if (root.TryGetProperty("rul", out var rul) &&
                rul.TryGetProperty("gbr", out var gbr) &&
                gbr.TryGetProperty("holdout", out var hold))
            {
                MetricsText =
                    $"Held-out B0018 (GBR ONNX): RUL RMSE {hold.GetProperty("rmse").GetDouble():0.0} cycles, " +
                    $"MAE {hold.GetProperty("mae").GetDouble():0.0}, R² {hold.GetProperty("r2").GetDouble():0.00}. " +
                    "SoH GBR RMSE 0.0067 (fraction). See README for leave-one-battery-out and noise robustness.";
            }

            return;
        }
    }
}
