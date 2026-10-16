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
            return;
        }

        Workspace.ScenarioAmbientC = AmbientC;
        Workspace.ScenarioCRate = CRate;
        var sim = Workspace.Service.Simulate(Workspace.Battery, new StressScenario
        {
            AmbientTemperatureC = AmbientC,
            DischargeCRate = CRate,
            CurrentCycle = Workspace.SelectedCycle?.CycleIndex,
        });

        AfText = $"AF = {sim.AccelerationFactor:0.00}  (temperature {sim.TemperatureAcceleration:0.00} × C-rate {sim.CRateAcceleration:0.00})";
        RulCompare =
            $"From cycle {sim.CurrentCycle}: baseline RUL {sim.BaselineRulCycles} cycles → " +
            $"stressed RUL {sim.StressedRulCycles} cycles " +
            $"({sim.AmbientTemperatureC:0} °C, {sim.DischargeCRate:0.00} C). " +
            $"EOL cycle {sim.BaselineEolCycle} → {sim.StressedEolCycle}" +
            (sim.StressedExtrapolated ? " (extrapolated past the measured window)." : ".");
        FadeSeries = ChartFactory.FadeSeries(Workspace.Battery, sim.Stressed);
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
