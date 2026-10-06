using BatteryHealth.App.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;

namespace BatteryHealth.App.Views;

public sealed partial class SimulatorPage : Page
{
    public SimulatorViewModel ViewModel { get; } = new(App.Workspace);

    public SimulatorPage()
    {
        InitializeComponent();
        ViewModel.Recalculate();
    }

    private void OnChanged(object sender, RangeBaseValueChangedEventArgs e) => ViewModel.Recalculate();

    private void OnReset(object sender, RoutedEventArgs e) => ViewModel.ResetReference();
}
