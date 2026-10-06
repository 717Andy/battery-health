using BatteryHealth.App.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BatteryHealth.App.Views;

public sealed partial class ForecastPage : Page
{
    public ForecastViewModel ViewModel { get; } = new(App.Workspace);

    public ForecastPage()
    {
        InitializeComponent();
        ViewModel.Refresh();
    }

    private void OnRefresh(object sender, RoutedEventArgs e) => ViewModel.Refresh();
}
