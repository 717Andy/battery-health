using BatteryHealth.App.Charts;
using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Simulation;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using LiveChartsCore;
using LiveChartsCore.SkiaSharpView;

namespace BatteryHealth.App.ViewModels;

public partial class SimulatorViewModel : ObservableObject
{
    public WorkspaceViewModel Workspace { get; }

    [ObservableProperty] private double ambientC = 24;
    [ObservableProperty] private double cRate = 1.0;
    [ObservableProperty] private string afText = "AF = 1.00";
    [ObservableProperty] private string eaBandText = "";
    [ObservableProperty] private string rulCompare = "Load a battery to simulate thermal and load stress.";
    [ObservableProperty] private string outlookText = "";
    [ObservableProperty] private string eaRulText = "";
    [ObservableProperty] private string extrapolatedText = "";
    [ObservableProperty] private string chartTitle = "Baseline fade vs stressed fade";
    [ObservableProperty] private string physicsNote = DegradationSimulator.ScenarioClaim;
    [ObservableProperty] private string emptyHint = "Load a cell log, or open the B0005 demo.";
    [ObservableProperty] private ISeries[] fadeSeries = [];

    public Axis[] CycleAxis { get; } = ChartFactory.CycleAxis();
    public Axis[] CapacityAxis { get; } = ChartFactory.CapacityAxis();

    public SimulatorViewModel(WorkspaceViewModel workspace)
    {
        Workspace = workspace;
        ambientC = workspace.ScenarioAmbientC;
        cRate = workspace.ScenarioCRate;
        workspace.BatteryChanged += (_, _) => Recalculate();
        workspace.CycleChanged += (_, _) => Recalculate();
    }

    [RelayCommand]
    public void ResetReference()
    {
        AmbientC = 24;
        CRate = 1.0;
    }

    public void Recalculate()
    {
        EmptyHint = Workspace.Battery is null ? "Load a cell log, or open the B0005 demo." : "";
        EaBandText = DescribeEaBand(AmbientC, CRate);
        if (Workspace.Battery is null)
        {
            FadeSeries = [];
            RulCompare = "Load a battery to simulate thermal and load stress.";
            OutlookText = "";
            EaRulText = "";
            ExtrapolatedText = "";
            ChartTitle = "Baseline fade vs stressed fade";
            return;
        }

        Workspace.ScenarioAmbientC = AmbientC;
        Workspace.ScenarioCRate = CRate;
        var outlook = StressOutlook.From(
            Workspace.Battery,
            AmbientC,
            CRate,
            Workspace.SelectedCycle?.CycleIndex);
        var sim = Workspace.Service.Simulate(Workspace.Battery, new StressScenario
        {
            AmbientTemperatureC = AmbientC,
            DischargeCRate = CRate,
            CurrentCycle = Workspace.SelectedCycle?.CycleIndex,
        });

        AfText = $"AF = {sim.AccelerationFactor:0.00}  (temperature {sim.TemperatureAcceleration:0.00} × C-rate {sim.CRateAcceleration:0.00})";
        RulCompare =
            $"Stress starts after cycle {outlook.StartCycle}. Capacity already lost stays as measured.";
        OutlookText =
            $"To 70% of the nameplate: baseline {outlook.BaselineTo70} cycles, stressed {outlook.StressedTo70} cycles. " +
            $"To 80% of the nameplate: baseline {outlook.BaselineTo80} cycles, stressed {outlook.StressedTo80} cycles.";
        EaRulText =
            $"Stressed cycles to 70% at 0.30 / 0.50 / 0.70 eV: {outlook.StressedTo70Ea030} / {outlook.StressedTo70Ea050} / {outlook.StressedTo70Ea070}. " +
            $"To 80%: {outlook.StressedTo80Ea030} / {outlook.StressedTo80Ea050} / {outlook.StressedTo80Ea070}. " +
            "The curve uses 0.50 eV.";
        ExtrapolatedText = outlook.StressedExtrapolated
            ? "Stressed end of life is past the last measured cycle."
            : "";
        ChartTitle = $"Stress applied after cycle {outlook.StartCycle}";
        FadeSeries = ChartFactory.FadeSeries(Workspace.Battery, outlook.StressedCurve, outlook.StartCycle);
    }

    internal static string DescribeEaBand(double ambientC, double cRate)
    {
        var low = DegradationSimulator.ScenarioAcceleration(ambientC, cRate, 0.30);
        var mid = DegradationSimulator.ScenarioAcceleration(ambientC, cRate, 0.50);
        var high = DegradationSimulator.ScenarioAcceleration(ambientC, cRate, 0.70);
        return
            $"At {ambientC:0} °C and {cRate:0.00} C, acceleration is {low:0.00} at 0.30 eV, " +
            $"{mid:0.00} at 0.50 eV, and {high:0.00} at 0.70 eV. These constants were not fit to the NASA cells.";
    }

    partial void OnAmbientCChanged(double value) => Recalculate();
    partial void OnCRateChanged(double value) => Recalculate();
}
