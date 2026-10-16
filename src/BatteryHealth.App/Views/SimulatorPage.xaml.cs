using BatteryHealth.App.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BatteryHealth.App.Views;

public sealed partial class SimulatorPage : Page
{
    public SimulatorViewModel ViewModel { get; } = new(App.Workspace);

    public SimulatorPage()
    {
        InitializeComponent();
        ViewModel.Recalculate();
    }

    private void OnReset(object sender, RoutedEventArgs e) => ViewModel.ResetReference();

    private async void OnLoadDemo(object sender, RoutedEventArgs e)
    {
        await App.Workspace.LoadFromPath(WorkspaceViewModel.DemoPath);
        ViewModel.Recalculate();
    }
}
