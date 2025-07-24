(function($){

  function computeBoundsAndJustify(ctx, nodes, width, height) {
    var borderx = 20, bordery = 20, r = 7, h = 13;
    ctx.font = '13px Arial';
    var bws = [], xs = [], ys = [];
    $.each(nodes, function (index, node) {
      var w = ctx.measureText(node.label).width;
      node.labelWidth = w;
      node.bw = w + r + r;
      node.bh = h + r + r;
      node.br = r;
      bws.push(node.bw);
      xs.push(node.x);
      ys.push(node.y);
    });
    var maxbw = Math.max.apply(Math, bws);
    var maxbh = h + r + r;
    var minx = Math.min.apply(Math, xs);
    var maxx = Math.max.apply(Math, xs);
    var miny = Math.min.apply(Math, ys);
    var maxy = Math.max.apply(Math, ys);
    var bx = borderx + maxbw / 2;
    var by = bordery + maxbh / 2;
    if(minx == maxx) {
      minx -= 1;
      maxx += 1;
    }
    if(miny == maxy) {
      miny -= 1;
      maxy += 1;
    }
    $.each(nodes, function (index, node) {
      node.x = bx + (node.x - minx) * (width - 2 * bx) / (maxx - minx);
      node.y = by + (node.y - miny) * (height - 2 * by) / (maxy - miny);
      node.bx = node.x - node.bw / 2;
      node.by = node.y - node.bh / 2;
    });
  }

  function drawNode(ctx, node) {
    ctx.font = '13px Arial';
    ctx.textBaseline = 'middle';
    var x = node.bx, y = node.by, r = node.br, w = node.bw, h = node.bh;
    ctx.fillText(node.label, x + r, y + h / 2);
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
    ctx.stroke();
  }

  function lerp(a, b, t) {
      return a + t * (b - a);
  }

  function evalBezierCurve(p1, p2, p3, p4, t) {
    var p12 = lerp(p1, p2, t), p23 = lerp(p2, p3, t), p34 = lerp(p3, p4, t);
    var p123 = lerp(p12, p23, t), p234 = lerp(p23, p34, t);
    return {pos: lerp(p123, p234, t), dir: p234 - p123};
  }

  function drawEdge(ctx, edge) {
    var p = [{x: edge.source.bx + edge.source.bw * 2 / 3,
              y: edge.source.by - 1,
              dx: 0, dy: -1},
             {x: edge.source.bx + edge.source.bw / 3,
              y: edge.source.by + edge.source.bh + 1,
              dx: 0, dy: +1},
             {x: edge.source.bx - 1,
              y: edge.source.by + edge.source.bh * 2 / 3,
              dx: -1, dy: 0},
             {x: edge.source.bx + edge.source.bw + 1,
              y: edge.source.by + edge.source.bh / 3,
              dx: +1, dy: 0},
             {x: edge.target.bx + edge.target.bw / 3,
              y: edge.target.by - 1,
              dx: 0, dy: -1},
             {x: edge.target.bx + edge.target.bw * 2 / 3,
              y: edge.target.by + edge.target.bh + 1,
              dx: 0, dy: +1},
             {x: edge.target.bx - 1,
              y: edge.target.by + edge.target.bh / 3,
              dx: -1, dy: 0},
             {x: edge.target.bx + edge.target.bw + 1,
              y: edge.target.by + edge.target.bh * 2 / 3,
              dx: +1, dy: 0}];
    var pIndexByDist = {}, dist = [];
    for (var i = 0; i < 4; i++) {
      for (var j = 4; j < 8; j++) {
        var distx = Math.abs(p[i].x - p[j].x),
            disty = Math.abs(p[i].y - p[j].y);
        dist.push(distx + disty);
        pIndexByDist[dist[dist.length - 1]] = [i, j];
      }
    }
    var pIndex = (edge.source === edge.target || dist.length === 0) ?
                 [0, 7] : pIndexByDist[Math.min.apply(Math, dist)];
    var p1 = p[pIndex[0]], p4 = p[pIndex[1]];
    var hs = 10, hw = 4;
    var x1 = p1.x, y1 = p1.y, x4 = p4.x + hs * p4.dx, y4 = p4.y + hs * p4.dy;
    var adx = Math.max(Math.abs(x1 - x4) / 3, 20),
        ady = Math.max(Math.abs(y1 - y4) / 3, 20);
    var x2 = x1 + p1.dx * adx, y2 = y1 + p1.dy * ady,
        x3 = x4 + p4.dx * adx, y3 = y4 + p4.dy * ady;

    ctx.strokeStyle = edge.color;
    ctx.fillStyle = edge.color;
    ctx.lineWidth = 2;

    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.bezierCurveTo(x2, y2, x3, y3, x4, y4);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(p4.x, p4.y)
    ctx.lineTo(x4 + hw * p4.dy, y4 - hw * p4.dx);
    ctx.lineTo(x4 - hw * p4.dy, y4 + hw * p4.dx);
    ctx.fill();

    var labelLayout = {};
    edge.labelLayout = labelLayout;
    if (x1 < x4) {
      labelLayout.x = evalBezierCurve(x1, x2, x3, x4, 3 / 5);
      labelLayout.y = evalBezierCurve(y1, y2, y3, y4, 3 / 5);
      labelLayout.textBaseline = 'bottom';
      labelLayout.margin = -2;
    } else {
      labelLayout.x = evalBezierCurve(x4, x3, x2, x1, 2 / 5);
      labelLayout.y = evalBezierCurve(y4, y3, y2, y1, 2 / 5);
      labelLayout.textBaseline = 'top';
      labelLayout.margin = 2;
    }
  }

  function drawEdgeLabel(ctx, edge) {
    ctx.save();

    var l = edge.labelLayout;
    var dx = l.x.dir, dy = l.y.dir;
    var d = Math.sqrt(dx * dx + dy * dy)
    dx /= d;
    dy /= d;
    ctx.textBaseline = l.textBaseline;
    ctx.font = '12px Arial';
    var measured = ctx.measureText(edge.label);

    ctx.setTransform(dx, dy, -dy, dx, l.x.pos, l.y.pos);

    // Halo effect
    ctx.save();
    ctx.shadowBlur = 5;
    ctx.shadowColor = 'White';
    ctx.fillStyle = 'White';
    for (var i = 0; i < 5; i++)
      ctx.fillText(edge.label, -measured.width / 2, l.margin);
    ctx.restore();

    ctx.fillStyle = edge.color;
    ctx.fillText(edge.label, -measured.width / 2, l.margin);

    ctx.restore();
  };

  function hexColor(r, g, b) {
    return '#' + (r < 16 ? '0' : '') + Math.floor(r).toString(16) +
                 (g < 16 ? '0' : '') + Math.floor(g).toString(16) +
                 (b < 16 ? '0' : '') + Math.floor(b).toString(16);
  }

  function saturatedColor(r, g, b) {
    var avg = (r + g + b) / 3;
    if (r < avg)
      r /= 2;
    if (g < avg)
      g /= 2;
    if (b < avg)
      b /= 2;
    return hexColor(r, g, b);
  }

  var colors = ['Black', 'Blue', 'Red', 'Green', 'Fuchsia'];

  function getActionColor(i) {
    if (i < colors.length)
      return colors[i];
    return saturatedColor(((i+70) * 30269) % 253, ((i+71) * 30307) % 253,
                          ((i+72) * 30323) % 253);
  }

  function layoutCircular(graph) {
    $.each(graph.nodes, function (index, node) {
      var radian = index * 2 * Math.PI / graph.nodes.length;
      node.x = Math.cos(radian);
      node.y = Math.sin(radian);
    });
  }

  $.documentReady(function() {
    $('.trac-workflow-graph').each(function (index) {
      var data = window['graph_' + this.id.slice(-12)];
      var width = data.width, height = data.height;
      var nodes = [], actions = [], edges = [];
      for (var i = 0; i < data.nodes.length; ++i)
        nodes.push({label: data.nodes[i]});
      for (var i = 0; i < data.actions.length; ++i)
        actions.push({label: data.actions[i], color: getActionColor(i)});
      for (var i = 0; i < data.edges.length; ++i) {
        var edge = data.edges[i];
        var sourceindex = edge[0], targetindex = edge[1], action = edge[2];
        action = actions[action];
        edges.push({label: action.label, color: action.color,
                    sourceindex: sourceindex, targetindex: targetindex,
                    source: nodes[sourceindex], target: nodes[targetindex]});
      }

      var canvas = $('<canvas>').css({width: width, height: height})[0];
      canvas.width = $(canvas).width();
      canvas.height = $(canvas).height();
      if (typeof(G_vmlCanvasManager) != 'undefined')
        canvas = G_vmlCanvasManager.initElement(canvas);
      $(this).empty().append(canvas);
      var ctx = canvas.getContext('2d');

      if (nodes.length == 0)
        return;

      var graph = {nodes: nodes, edges: edges};
      layoutCircular(graph);
      computeBoundsAndJustify(ctx, nodes, width, height);

      $.each(nodes, function (index, node) {
        drawNode(ctx, node);
      });
      $.each(edges, function (index, edge) {
        drawEdge(ctx, edge);
      });
      $.each(edges, function (index, edge) {
        drawEdgeLabel(ctx, edge);
      });
    });
  });

})(jQuery);
