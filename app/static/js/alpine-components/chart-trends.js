// chart-trends.js — chartTrends Alpine component (Phase 19 / Plan 06 VIZ-01).
//
// Renders two Chart.js v4 canvases:
//   1. rating-over-time — line chart of brew + cafe session ratings over the last 90 days
//   2. flavor-distribution — horizontal bar chart of top-15 flavor descriptors
//
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data() inside
// 'alpine:init'. No eval. Canvas sized via CSS class (.chart-canvas) + explicit
// width/height HTML attrs + maintainAspectRatio:false (RESEARCH Pitfall 3).
// Chart.js 4.5.1 UMD does not use eval — safe under strict CSP with nonce on
// the script tag (RESEARCH Pattern 6).
//
// Dark-mode: watches document.documentElement classList for 'dark' (Tailwind v3
// darkMode:'selector'); reconfigures chart colors on toggle without page reload.
// Light palette: espresso-700 (#3D2817) lines on cream-100 (#F4EFE6) grid lines.
// Dark palette:  cream-200 (#E3D5C9) lines on espresso-800 (#2B1B10) grid lines.
//
// Load order: MUST load before @alpinejs/csp core in base.html, and Chart.js CDN
// MUST load before this file so window.Chart is available when Alpine boots.
// (base.html script ordering ensures this — plan 19-06 Task 1.)

document.addEventListener('alpine:init', function () {
  Alpine.data('chartTrends', function (ratingsUrl, flavorsUrl) {
    return {
      ratingsUrl: ratingsUrl,
      flavorsUrl: flavorsUrl,
      _ratingChart: null,
      _flavorChart: null,
      _observer: null,

      // --------------- color helpers ---------------

      _isDark: function () {
        return document.documentElement.classList.contains('dark');
      },

      _palette: function () {
        var dark = this._isDark();
        return {
          lineColor:   dark ? '#E3D5C9' : '#3D2817',  // cream-200 / espresso-700
          pointColor:  dark ? '#E3D5C9' : '#3D2817',
          gridColor:   dark ? '#2B1B10' : '#E3D5C9',  // espresso-800 / cream-200
          tickColor:   dark ? '#DACBAE' : '#4B3422',  // cream-300  / espresso-600
          bgColor:     dark ? '#21150C' : '#F4EFE6',  // espresso-900 / cream-100
          barColor:    dark ? '#C6AB94' : '#3D2817',  // espresso-200 / espresso-700
        };
      },

      // --------------- chart init ---------------

      init: function () {
        var self = this;

        // Only proceed if Chart.js is loaded (guard for environments where CDN is blocked)
        if (typeof window.Chart === 'undefined') {
          return;
        }

        // Fetch both data sources in parallel then build charts
        Promise.all([
          fetch(self.ratingsUrl).then(function (r) { return r.ok ? r.json() : []; }),
          fetch(self.flavorsUrl).then(function (r) { return r.ok ? r.json() : []; }),
        ]).then(function (results) {
          var ratingsData = results[0];
          var flavorsData = results[1];
          self._buildRatingChart(ratingsData);
          self._buildFlavorChart(flavorsData);
          self._watchDark();
        }).catch(function () {
          // Silently ignore — chart area stays blank, not an error state
        });
      },

      // --------------- rating-over-time line chart ---------------

      _buildRatingChart: function (data) {
        var canvas = this.$refs.ratingCanvas;
        if (!canvas) { return; }
        var p = this._palette();
        var labels = data.map(function (d) { return d.date; });
        var values = data.map(function (d) { return d.rating; });

        this._ratingChart = new window.Chart(canvas, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [{
              label: 'Rating',
              data: values,
              borderColor: p.lineColor,
              backgroundColor: p.lineColor,
              pointBackgroundColor: p.pointColor,
              pointRadius: 4,
              tension: 0.2,
              fill: false,
            }],
          },
          options: {
            maintainAspectRatio: false,
            animation: false,
            plugins: {
              legend: { display: false },
            },
            scales: {
              x: {
                grid: { color: p.gridColor },
                ticks: { color: p.tickColor, maxTicksLimit: 8, maxRotation: 30 },
              },
              y: {
                min: 0,
                max: 5,
                grid: { color: p.gridColor },
                ticks: { color: p.tickColor, stepSize: 1 },
              },
            },
          },
        });
      },

      // --------------- flavor-distribution horizontal bar chart ---------------

      _buildFlavorChart: function (data) {
        var canvas = this.$refs.flavorCanvas;
        if (!canvas) { return; }
        var p = this._palette();
        var labels = data.map(function (d) { return d.descriptor; });
        var counts = data.map(function (d) { return d.count; });

        this._flavorChart = new window.Chart(canvas, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [{
              label: 'Sessions',
              data: counts,
              backgroundColor: p.barColor,
              borderColor: p.barColor,
              borderWidth: 1,
            }],
          },
          options: {
            indexAxis: 'y',
            maintainAspectRatio: false,
            animation: false,
            plugins: {
              legend: { display: false },
            },
            scales: {
              x: {
                grid: { color: p.gridColor },
                ticks: { color: p.tickColor },
              },
              y: {
                grid: { display: false },
                ticks: { color: p.tickColor },
              },
            },
          },
        });
      },

      // --------------- dark-mode observer ---------------

      _watchDark: function () {
        var self = this;
        self._observer = new MutationObserver(function (mutations) {
          mutations.forEach(function (m) {
            if (m.attributeName === 'class') {
              self._retheme();
            }
          });
        });
        self._observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
      },

      _retheme: function () {
        var p = this._palette();
        var charts = [this._ratingChart, this._flavorChart];
        charts.forEach(function (chart) {
          if (!chart) { return; }
          var ds = chart.data.datasets[0];
          if (!ds) { return; }
          ds.borderColor = p.lineColor;
          ds.backgroundColor = p.lineColor;
          if (ds.pointBackgroundColor !== undefined) {
            ds.pointBackgroundColor = p.pointColor;
          }
          chart.options.scales.x.grid.color = p.gridColor;
          chart.options.scales.x.ticks.color = p.tickColor;
          chart.options.scales.y.grid.color = p.gridColor;
          chart.options.scales.y.ticks.color = p.tickColor;
          chart.update();
        });

        // Flavor chart uses barColor not lineColor
        if (this._flavorChart) {
          var fds = this._flavorChart.data.datasets[0];
          if (fds) {
            fds.backgroundColor = p.barColor;
            fds.borderColor = p.barColor;
            this._flavorChart.update();
          }
        }
      },

      // --------------- cleanup ---------------

      destroy: function () {
        if (this._observer) { this._observer.disconnect(); }
        if (this._ratingChart) { this._ratingChart.destroy(); }
        if (this._flavorChart) { this._flavorChart.destroy(); }
      },
    };
  });
});
