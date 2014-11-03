      var gridster, static_grid;

      $(function(){
        gridster = $(".gridster ul").gridster({
          widget_base_dimensions: [200, 200],
          widget_margins: [6, 6],
          //helper: 'clone'
        }).data('gridster');
        gridster.$el
          .on('mouseenter', '> li', function() {
              gridster.resize_widget($(this), 3, 3);
          })
          .on('mouseleave', '> li', function() {
              gridster.resize_widget($(this), 1, 1);
          });
      });