import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# Data with method information
prefetchers = {
    'SMS': {'storage': 116.6, 'speedup': 1.226, 'method': 'PC + Addr'},
    'DSPatch': {'storage': 4.25, 'speedup': 1.153, 'method': 'PC'},
    'PMP': {'storage': 5.0, 'speedup': 1.177, 'method': 'Offset'},
    'Gaze': {'storage': 4.46, 'speedup': 1.238, 'method': 'Two Offsets'},
    'STEP': {'storage': 10.4, 'speedup': 1.28, 'method': ''},
    # 'Bingo': {'storage': 122.8, 'speedup': 1.277, 'method': 'PC + Addr/Offset'},
    # 'Bingo-10KB': {'storage': 10.1, 'speedup': 1.246, 'method': ''},
    'eBingo-10KB': {'storage': 10.2, 'speedup': 1.259, 'method': 'PC + Addr/Offset'},
    'eBingo': {'storage': 124.8, 'speedup': 1.279, 'method': 'PC + Addr/Offset'},
}

# Create figure with lower height
fig, ax = plt.subplots(figsize=(9, 6))

# Set background color
ax.set_facecolor('#f8f9fa')
fig.patch.set_facecolor('white')

# Plot all points
for name in prefetchers.keys():
    x = prefetchers[name]['storage']
    y = prefetchers[name]['speedup']
    
    if name == 'STEP':
        ax.scatter(x, y, s=250, c='#e74c3c', marker='o', 
                   edgecolors='#c0392b', linewidths=3, zorder=5, )
    if name == "STEP_L":
        ax.scatter(x, y, s=250, c='#e74c3c', marker='o', 
                   edgecolors='#c0392b', linewidths=3, zorder=5, )
    else:
        ax.scatter(x, y, s=180, c='#34495e', marker='o', 
                   edgecolors='#2c3e50', linewidths=2, alpha=0.75, zorder=4)
    
    # Add name labels
    offset_x = 12 if name != 'Bingo' else -42
    offset_y = 0.8 if name not in ['STEP', 'Gaze'] else -0.8
    
    ax.annotate(name, (x, y), xytext=(offset_x, offset_y), 
                textcoords='offset points', fontsize=11, 
                fontweight='bold' if name == 'STEP' else 'semibold',
                color='#c0392b' if name == 'STEP' else '#2c3e50')
    
    # Add method information below each point
    if prefetchers[name]['method']:
        method_offset_y = -20
        ax.annotate(f"({prefetchers[name]['method']})", (x, y), 
                    xytext=(offset_x , method_offset_y), 
                    textcoords='offset points', fontsize=12, 
                    style='italic', color='#7f8c8d')

# Labels with better styling
ax.set_xlabel('Storage (KB)', fontsize=13, fontweight='bold', color='#2c3e50')
ax.set_ylabel('Speedup', fontsize=13, fontweight='bold', color='#2c3e50')

# Grid with subtle styling
ax.grid(True, alpha=0.25, linestyle='-', linewidth=0.5, color='#bdc3c7')
ax.set_axisbelow(True)

# Set axis limits
ax.set_xlim(-8, 152)
ax.set_ylim(1.14, 1.29)

# Customize spines
for spine in ax.spines.values():
    spine.set_edgecolor('#95a5a6')
    spine.set_linewidth(1.5)

# Legend with better styling
legend = ax.legend(loc='lower right', fontsize=11, frameon=True, 
                   fancybox=True, shadow=True, framealpha=0.95)
legend.get_frame().set_facecolor('white')
legend.get_frame().set_edgecolor('#95a5a6')

# Tick parameters
ax.tick_params(axis='both', which='major', labelsize=10, colors='#2c3e50')

plt.tight_layout()

# Save as PDF
plt.savefig('prefetcher_comparison.pdf', format='pdf', bbox_inches='tight', dpi=300)
print("Graph saved as 'prefetcher_comparison.pdf'")