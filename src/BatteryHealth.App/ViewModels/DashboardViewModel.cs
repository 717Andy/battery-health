using BatteryHealth.App.Charts;
using BatteryHealth.Core.Domain;
using CommunityToolkit.Mvvm.ComponentModel;
using LiveChartsCore;
using LiveChartsCore.SkiaSharpView;

namespace BatteryHealth.App.ViewModels;

public partial class DashboardViewModel : ObservableObject
{
    public WorkspaceViewModel Workspace { get; }

    [ObservableProperty] private ISeries[] sensorSeries = [];
    [ObservableProperty] private ISeries[] fadeSeries = [];
    [ObservableProperty] private string cycleCaption = "Select a discharge cycle with a sensor trace.";
    [ObservableProperty] private string emptyHint = "Open a processed NASA JSON (data/processed/B0005.json) or the bundled B0005 demo.";
    [ObservableProperty] private double cycleSlider = 1;
    [ObservableProperty] private double cycleMin = 1;
    [ObservableProperty] private double cycleMax = 1;

    public Axis[] TimeAxis { get; } = ChartFactory.TimeAxis();
    public Axis[] SensorYAxis { get; } = ChartFactory.SensorYAxis();
    public Axis[] CycleAxis { get; } = ChartFactory.CycleAxis();
    public Axis[] CapacityAxis { get; } = ChartFactory.CapacityAxis();

    public DashboardViewModel(WorkspaceViewModel workspace)
    {
        Workspace = workspace;
        workspace.BatteryChanged += (_, _) => Refresh();
        workspace.CycleChanged += (_, _) => Refresh();
    }

    public void Refresh()
    {
        var battery = Workspace.Battery;
        if (battery is null)
        {
            SensorSeries = [];
            FadeSeries = [];
            return;
        }

        var discharges = battery.DischargeCycles.ToList();
        CycleMin = discharges.FirstOrDefault()?.CycleIndex ?? 1;
        CycleMax = discharges.LastOrDefault()?.CycleIndex ?? 1;
        if (Workspace.SelectedCycle is { } selected)
        {
            CycleSlider = selected.CycleIndex;
            CycleCaption = selected.HasTrace
                ? $"Cycle {selected.CycleIndex} · {selected.Type} · {(selected.CapacityAh is { } c ? $"{c:0.000} Ah" : "no capacity")}"
                : $"Cycle {selected.CycleIndex} has fade data only. Pick a traced cycle (demo: 1, 40, 80, 120, last).";
        }

        SensorSeries = ChartFactory.SensorSeries(Workspace.SelectedCycle);
        FadeSeries = ChartFactory.FadeSeries(battery);
    }

    public void OnCycleSlider(int value)
    {
        Workspace.SelectCycle(value);
    }
}
