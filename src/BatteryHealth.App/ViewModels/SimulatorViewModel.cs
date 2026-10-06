using BatteryHealth.App.Charts;
using BatteryHealth.Core.Domain;
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
    [ObservableProperty] private string rulCompare = "Load a battery to simulate thermal and load stress.";
    [ObservableProperty] private string physicsNote =
        "Arrhenius temperature acceleration (Ea = 0.50 eV) × C-rate power law (C/1C)^0.60, referenced to the NASA 24 °C / 1C protocol.";
    [ObservableProperty] private ISeries[] fadeSeries = [];

    public Axis[] CycleAxis { get; } = ChartFactory.CycleAxis();
    public Axis[] CapacityAxis { get; } = ChartFactory.CapacityAxis();

    public SimulatorViewModel(WorkspaceViewModel workspace)
    {
        Workspace = workspace;
        workspace.BatteryChanged += (_, _) => Recalculate();
        workspace.CycleChanged += (_, _) => Recalculate();
    }

    [RelayCommand]
    public void ResetReference()
    {
        AmbientC = 24;
        CRate = 1.0;
        Recalculate();
    }

    public void Recalculate()
    {
        if (Workspace.Battery is null)
        {
            FadeSeries = [];
            return;
        }

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

    partial void OnAmbientCChanged(double value) => Recalculate();
    partial void OnCRateChanged(double value) => Recalculate();
}
