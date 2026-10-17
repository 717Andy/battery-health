using System.Collections.ObjectModel;
using BatteryHealth.App.Charts;
using BatteryHealth.Core.Domain;
using CommunityToolkit.Mvvm.ComponentModel;
using Microsoft.UI.Xaml;
using LiveChartsCore;
using LiveChartsCore.SkiaSharpView;

namespace BatteryHealth.App.ViewModels;

public partial class DashboardViewModel : ObservableObject
{
    public WorkspaceViewModel Workspace { get; }

    [ObservableProperty] private ISeries[] sensorSeries = [];
    [ObservableProperty] private ISeries[] fadeSeries = [];
    [ObservableProperty] private string cycleCaption = "Select a discharge cycle with a sensor trace.";
    [ObservableProperty] private string emptyHint = IntakeReport.StartingHint;
    [ObservableProperty] private string intakeText = "";
    [ObservableProperty] private Visibility intakeVisibility = Visibility.Collapsed;
    [ObservableProperty] private double ratedAh = 2;
    [ObservableProperty] private int selectedRowIndex = -1;

    public ObservableCollection<DischargeChoice> DischargeRows { get; } = [];

    private bool _syncing;

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
        _syncing = true;
        DischargeRows.Clear();
        if (battery is null)
        {
            SelectedRowIndex = -1;
            IntakeText = "";
            IntakeVisibility = Visibility.Collapsed;
            EmptyHint = IntakeReport.StartingHint;
            _syncing = false;
            SensorSeries = [];
            FadeSeries = [];
            return;
        }

        var intake = IntakeReport.From(battery);
        IntakeText = string.Join(Environment.NewLine, intake.Lines);
        IntakeVisibility = Visibility.Visible;
        EmptyHint = "";

        var discharges = battery.DischargeCycles.ToList();
        foreach (var cycle in discharges)
        {
            var capacity = cycle.CapacityAh is { } value ? $"{value:0.000} Ah" : "no capacity";
            var trace = cycle.HasTrace ? "trace" : "fade only";
            DischargeRows.Add(new DischargeChoice
            {
                CycleIndex = cycle.CycleIndex,
                Label = $"Cycle {cycle.CycleIndex} · {capacity} · {trace}",
            });
        }

        RatedAh = battery.RatedCapacityAh;
        SelectedRowIndex = Workspace.SelectedCycle is { } selected
            ? discharges.FindIndex(c => c.CycleIndex == selected.CycleIndex)
            : -1;
        _syncing = false;

        if (Workspace.SelectedCycle is { } current)
        {
            CycleCaption = current.HasTrace
                ? $"Cycle {current.CycleIndex} · {current.Type} · {(current.CapacityAh is { } c ? $"{c:0.000} Ah" : "no capacity")}"
                : $"Cycle {current.CycleIndex} has fade data only.";
        }

        SensorSeries = ChartFactory.SensorSeries(Workspace.SelectedCycle);
        FadeSeries = ChartFactory.FadeSeries(battery, selectedCycle: Workspace.SelectedCycle?.CycleIndex);
    }

    partial void OnSelectedRowIndexChanged(int value)
    {
        if (_syncing || value < 0 || value >= DischargeRows.Count)
        {
            return;
        }

        Workspace.SelectCycle(DischargeRows[value].CycleIndex);
    }

    partial void OnRatedAhChanged(double value)
    {
        if (_syncing || Workspace.Battery is null || value <= 0)
        {
            return;
        }

        _ = Workspace.SetRatedCapacityAsync(value);
    }
}

public sealed class DischargeChoice
{
    public int CycleIndex { get; init; }
    public string Label { get; init; } = "";

    public override string ToString() => Label;
}
