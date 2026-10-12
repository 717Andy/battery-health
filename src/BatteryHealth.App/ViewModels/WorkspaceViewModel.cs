using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.UI.Dispatching;

namespace BatteryHealth.App.ViewModels;

public sealed class TrajectorySnapshot
{
    public required BatteryRecord Battery { get; init; }
    public IReadOnlyList<ForecastResult> Points { get; init; } = [];
    public string? Error { get; init; }
}

/// <summary>Shared session for the three Fluent pages.</summary>
public partial class WorkspaceViewModel : ObservableObject
{
    private readonly object _gate = new();
    private BatteryAnalyticsService? _service;

    [ObservableProperty] private BatteryRecord? battery;
    [ObservableProperty] private BatteryCycle? selectedCycle;
    [ObservableProperty] private ForecastResult? forecast;
    [ObservableProperty] private string status = "Load a NASA processed JSON or a CALCE CSV/Excel log.";
    [ObservableProperty] private string? errorMessage;
    [ObservableProperty] private bool isBusy;
    [ObservableProperty] private string batteryTitle = "No battery loaded";
    [ObservableProperty] private string summaryLine = "Fleet diagnostic — local ONNX, no cloud.";
    [ObservableProperty] private TrajectorySnapshot? trajectory;

    public IReadOnlyList<BatteryCycle> DischargeCycles =>
        Battery?.DischargeCycles.ToList() ?? [];

    public BatteryAnalyticsService Service => _service ??= new BatteryAnalyticsService();

    public event EventHandler? BatteryChanged;
    public event EventHandler? CycleChanged;

    [RelayCommand]
    public async Task LoadFromPath(string path)
    {
        var ui = DispatcherQueue.GetForCurrentThread();
        Post(ui, () =>
        {
            IsBusy = true;
            ErrorMessage = null;
            Status = "Loading…";
        });

        try
        {
            var loaded = await Task.Run(() =>
            {
                lock (_gate)
                {
                    var record = Service.Load(path);
                    IReadOnlyList<ForecastResult> points = [];
                    string? trajectoryError = null;
                    try
                    {
                        points = Service.ForecastTrajectory(record);
                    }
                    catch (Exception ex)
                    {
                        trajectoryError = ex.Message;
                    }

                    return (record, points, trajectoryError);
                }
            });

            Post(ui, () => ApplyLoaded(path, loaded.record, loaded.points, loaded.trajectoryError));
        }
        catch (Exception ex)
        {
            Post(ui, () =>
            {
                ErrorMessage = ex.Message;
                Status = "Could not load file.";
                IsBusy = false;
            });
        }
    }

    public void SelectCycle(int cycleIndex)
    {
        if (Battery is null)
        {
            return;
        }

        var next = Battery.CycleAt(cycleIndex);
        if (ReferenceEquals(next, SelectedCycle))
        {
            return;
        }

        SelectedCycle = next;
        RefreshForecast();
        CycleChanged?.Invoke(this, EventArgs.Empty);
    }

    public void RefreshForecast()
    {
        if (Battery is null || SelectedCycle is null)
        {
            Forecast = null;
            return;
        }

        try
        {
            lock (_gate)
            {
                Forecast = Service.Forecast(Battery, SelectedCycle.CycleIndex);
            }

            if (Trajectory?.Error is null)
            {
                ErrorMessage = null;
            }
        }
        catch (Exception ex)
        {
            Forecast = null;
            ErrorMessage = ex.Message;
        }
    }

    private void ApplyLoaded(
        string path,
        BatteryRecord record,
        IReadOnlyList<ForecastResult> points,
        string? trajectoryError)
    {
        var discharges = record.DischargeCycles.ToList();
        var first = discharges.FirstOrDefault()?.CapacityAh;
        var last = discharges.LastOrDefault()?.CapacityAh;
        Battery = record;
        Trajectory = new TrajectorySnapshot
        {
            Battery = record,
            Points = points,
            Error = trajectoryError,
        };
        BatteryTitle = $"{record.BatteryId} · {record.Source.ToUpperInvariant()}";
        SummaryLine =
            $"{discharges.Count} discharge cycles · rated {record.RatedCapacityAh:0.00} Ah · " +
            $"EOL {record.EolCapacityFraction:P0} ({record.EolCapacityAh:0.00} Ah) · " +
            $"capacity {first:0.000} → {last:0.000} Ah";
        Status = $"Loaded {path}";
        ErrorMessage = trajectoryError;
        SelectedCycle = discharges.LastOrDefault(c => c.HasTrace) ?? discharges.LastOrDefault();
        try
        {
            RefreshForecast();
            OnPropertyChanged(nameof(DischargeCycles));
            BatteryChanged?.Invoke(this, EventArgs.Empty);
            CycleChanged?.Invoke(this, EventArgs.Empty);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private static void Post(DispatcherQueue? queue, Action action)
    {
        if (queue is null || queue.HasThreadAccess)
        {
            action();
            return;
        }

        queue.TryEnqueue(() => action());
    }
}
