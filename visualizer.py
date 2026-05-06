import matplotlib.pyplot as plt

class WifiVisualizer:
    """
    Handles the live graphing of Wi-Fi signal data.
    """
    
    def __init__(self, window_size=50):
        # Interactive mode on for live updates
        plt.ion()
        
        self.window_size = window_size
        self.data_x = [] # Time or sample index
        self.data_y = [] # Signal percentage
        
        # Setup the plot
        self.fig, self.ax = plt.subplots(figsize=(10, 5))
        self.line, = self.ax.plot([], [], color='#007acc', linewidth=2)
        
        # Add labels and styling
        self.ax.set_title("WiWave Motion: Live Signal Strength", fontsize=14)
        self.ax.set_xlabel("Recent Samples", fontsize=10)
        self.ax.set_ylabel("Signal Strength (%)", fontsize=10)
        self.ax.set_ylim(0, 105) # Wi-Fi is 0-100%
        self.ax.grid(True, linestyle='--', alpha=0.6)
        
        # Text element to show motion status
        self.status_text = self.ax.text(0.02, 0.95, "", transform=self.ax.transAxes, 
                                        fontsize=12, fontweight='bold', verticalalignment='top')

    def update(self, new_signal, status):
        """
        Updates the graph with a new reading.
        
        Args:
            new_signal (int): The current signal strength percentage.
            status (str): The current motion status (CALM or MOTION).
        """
        if new_signal is None:
            return
            
        # Add new data point
        self.data_y.append(new_signal)
        self.data_x.append(len(self.data_y))
        
        # Scroll the window (only show the last X samples)
        if len(self.data_y) > self.window_size:
            display_y = self.data_y[-self.window_size:]
            display_x = range(len(display_y))
        else:
            display_y = self.data_y
            display_x = range(len(display_y))
            
        # Update the line data
        self.line.set_data(display_x, display_y)
        self.ax.set_xlim(0, self.window_size)
        
        # Update status text and color
        self.status_text.set_text(f"STATUS: {status}")
        if "MOTION" in status:
            self.status_text.set_color('red')
        else:
            self.status_text.set_color('green')
            
        # Refresh the plot
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

    def is_closed(self):
        """Checks if the user closed the graph window."""
        return not plt.fignum_exists(self.fig.number)

if __name__ == "__main__":
    # Test visualizer with fake data
    import time
    import random
    
    print("Opening visualizer test...")
    viz = WifiVisualizer()
    
    try:
        for i in range(100):
            fake_signal = random.randint(90, 95)
            viz.update(fake_signal, "CALM / NO MOTION")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Visualizer closed.")
