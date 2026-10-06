using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Inference;
using BatteryHealth.Core.Parsing;
using BatteryHealth.Core.Simulation;

namespace BatteryHealth.Core.Services;

/// <summary>
/// Facade used by the WinUI app and the Linux CLI.
/// </summary>
public sealed class BatteryAnalyticsService : IDisposable
{
    private readonly OnnxBatteryPredictor _predictor;

    public BatteryAnalyticsService(string? modelDirectory = null)
    {
        _predictor = new OnnxBatteryPredictor(modelDirectory);
    }

    public BatteryRecord Load(string path) => BatteryFileLoader.Load(path);

    public ForecastResult Forecast(BatteryRecord battery, int? cycleIndex = null)
    {
        var cycle = cycleIndex is { } idx
            ? battery.CycleAt(idx) ?? throw new ArgumentOutOfRangeException(nameof(cycleIndex))
            : battery.DischargeCycles.LastOrDefault()
              ?? throw new InvalidOperationException("No discharge cycles");
        return _predictor.Predict(battery, cycle);
    }

    public IReadOnlyList<ForecastResult> ForecastTrajectory(BatteryRecord battery) =>
        _predictor.PredictAll(battery);

    public StressSimulation Simulate(BatteryRecord battery, StressScenario scenario) =>
        DegradationSimulator.Simulate(battery, scenario);

    public void Dispose() => _predictor.Dispose();
}
