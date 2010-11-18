// Log graph painting

(function($){

  $.paintLogGraph = function(graph, canvas) {
    var ctx = canvas.getContext('2d');
    ctx.scale(-canvas.width / graph.columns,
              canvas.height / graph.vertices.length);
    ctx.translate(-graph.columns + 0.5, 0.5)
    
    // Paint threads
    ctx.lineWidth = graph.line_width;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    var threads = graph.threads;
    for (var i = 0; i < threads.length; ++i) {
      var thread = threads[i];
      ctx.strokeStyle = graph.colors[i % graph.colors.length];
      ctx.beginPath();
      for (var j = 0; j < thread.length; ++j) {
        var item = thread[j];
        if (item[0] == 0)
          ctx.moveTo(item[1], item[2]);
        else if (item[0] == 1)
          ctx.lineTo(item[1], item[2]);
      }
      ctx.stroke();
    }
    
    // Paint dots
    ctx.lineWidth = 0;
    var vertices = graph.vertices;
    for (var i = 0; i < vertices.length; ++i) {
      var vertice = vertices[i];
      ctx.fillStyle = graph.colors[vertice[1] % graph.colors.length];
      ctx.beginPath();
      ctx.arc(vertice[0], i, graph.dot_radius, 0, 2 * Math.PI, true);
      ctx.fill();
    }
    
    return canvas;
  };

})(jQuery);
