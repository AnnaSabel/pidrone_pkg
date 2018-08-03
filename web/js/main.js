/**
* Setup all visualization elements when the page is loaded.
*/
function empty(element) {
while (element.firstChild) {
  element.removeChild(element.firstChild);
}
}
function printProperties(obj) {
for(var propt in obj){
  console.log(propt + ': ' + obj[propt]);
}
}

function myround(number, precision) {
  var factor = Math.pow(10, precision);
  var tempNumber = number * factor;
  var roundedTempNumber = Math.round(tempNumber);
  return roundedTempNumber / factor;
};

var markerClient;
var ros;
var modepub;
var modeMsg;
var heartbeatPub;

function closeSession(){
  console.log("Closing connections.");
  ros.disconnect();
  return false;
}

function init() {
    // Connect to ROS.
    var url = 'ws://' + document.getElementById('hostname').value + ':9090'
    ros = new ROSLIB.Ros({
        url : url
    });

  ros.on('error', function(error) {
      console.log('ROS Master:  Error, check console.');
      //printProperties(error);
      document.getElementById('statusMessage').innerHTML='Error detected; check console.';
      $('#statusMessage').addClass('alert-danger').removeClass('alert-success');
  });

  ros.on('connection', function() {
      console.log('ROS Master:  Connected.');
      //printProperties(error);
      document.getElementById('statusMessage').innerHTML="Connected";
      $('#statusMessage').addClass('alert-success').removeClass('alert-danger');
  });

  ros.on('close', function() {
      console.log('ROS Master:  Connection closed.');
      //printProperties(error);
      document.getElementById('statusMessage').innerHTML="Disconnected";
      $('#statusMessage').addClass('alert-danger').removeClass('alert-success');
  });

    modepub = new ROSLIB.Topic({
      ros : ros,
      name : '/pidrone/set_mode',
      messageType : 'pidrone_pkg/Mode'
    });

    modeMsg = new ROSLIB.Message({
      mode: 0,
     });

    emptyMsg = new ROSLIB.Message({
     });


    heartbeatPub = new ROSLIB.Topic({
      ros : ros,
      name : '/pidrone/heartbeat',
      messageType : 'std_msgs/String'
    });
    heartbeatpubmsg = new ROSLIB.Message({data: "Javascript API"})

    setInterval(function(){
      heartbeatPub.publish(heartbeatpubmsg);
      //console.log("heartbeat");
    }, 1000);

    resetpub = new ROSLIB.Topic({
      ros : ros,
      name : '/pidrone/reset_transform',
      messageType : 'std_msgs/Empty'
    });

    togglepub = new ROSLIB.Topic({
      ros : ros,
      name : '/pidrone/toggle_transform',
      messageType : 'std_msgs/Empty'
    });

    statesub = new ROSLIB.Topic({
      ros : ros,
      name : '/pidrone/state',
      messageType : 'pidrone_pkg/State',
      queue_length : 2,
      throttle_rate : 2
    });
    statesub.subscribe(function(message) {
      //printProperties(message);
      var mynumber = myround(message.vbat, 2);
      document.getElementById('vbat').innerHTML=mynumber
      if (message.vbat <= 11.3) {
        document.getElementById('vbat').innerHTML=mynumber + " EMPTY!";
        $('#vbat').addClass('alert-danger').removeClass('alert-success');
      } else {
        document.getElementById('vbat').innerHTML=mynumber;
        $('#vbat').addClass('alert-success').removeClass('alert-danger');
      }

    });


    irsub = new ROSLIB.Topic({
      ros : ros,
      name : '/pidrone/infrared',
      messageType : 'sensor_msgs/Range',
      queue_length : 2,
      throttle_rate : 5
    });
    irsub.subscribe(function(message) {
      //printProperties(message);
      //console.log("Range: " + message.range);
      irChart.data.datasets[0].data[count] = message.range;
      if (count - 1 < 0) {
        irChart.data.datasets[1].data[windowSize - 1] = 0;
      } else{
        irChart.data.datasets[1].data[count - 1] = 0;
      }
      irChart.data.datasets[1].data[count] = 60;
      count = count + 1;
      count = count % irChart.data.datasets[0].data.length;
      irChart.update();
      //console.log("Data: " + irChart.data.datasets[0].data);

    });

  
    var imu = document.getElementById("imu");
    empty(imu);

    // Create the main viewer.
    var imuviewer = new ROS3D.Viewer({
      divID : 'imu',
      width : 320,
      height : 240,
      antialias : true
    });


    // Setup a client to listen to TFs.
    var tfClient = new ROSLIB.TFClient({
      ros : ros,
      angularThres : 0.01,
      transThres : 0.01,
      rate : 5.0,
      fixedFrame : '/base'
    });

    // Setup the marker client.
    markerClient = new ROS3D.MarkerClient({
      ros : ros,
      tfClient : tfClient,
      topic : document.getElementById('imutopic').value,
      rate : 5.0,
      rootObject : imuviewer.scene
    });


    // Create the main viewer.
//    var imageviewer = new MJPEGCANVAS.Viewer({
//      divID : 'camera',
//      host : '192.168.42.1',
//      width : 320,
//      height : 240,
//      topic : '/pidrone/picamera/image_raw'
//    });



    imageStream();
  }

  function imageStream() {
    var image = document.getElementById('cameraImage');
    image.src = "http://" + document.getElementById('hostname').value + ":8080/stream?topic=/pidrone/picamera/image_raw&quality=70";

    var firstImage = document.getElementById('firstImage');
    firstImage.src = "http://" + document.getElementById('hostname').value + ":8080/stream?topic=/pidrone/picamera/first_image&quality=70";

  }

  function markerUpdate() {
    markerClient.topicName = document.getElementById('imutopic').value;
    markerClient.subscribe();
  }

function publishArm() {
  console.log("arm");
  modeMsg.mode = 0
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}
function publishResetTransform() {
  console.log("reset transform");
  resetpub.publish(emptyMsg);
}

function publishToggleTransform() {
  console.log("toggle transform");
  togglepub.publish(emptyMsg);
}


function publishDisarm() {
  console.log("disarm");
  modeMsg.mode = 4
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}

function publishZeroVelocity() {
  console.log("zero velocity");
  modeMsg.mode = 5
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}


function publishTakeoff() {
  console.log("takeoff");
  modeMsg.mode = 5
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}


function publishTranslateLeft() {
  console.log("translate left");
  modeMsg.mode = 5
  modeMsg.x_velocity = -10
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}

function publishTranslateRight() {
  console.log("translate right");
  modeMsg.mode = 5
  modeMsg.x_velocity = 10
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}

function publishTranslateForward() {
  console.log("translate forward");
  modeMsg.mode = 5
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 10
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);

}

function publishTranslateBackward() {
  console.log("translate backward");
  modeMsg.mode = 5
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = -10
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}


function publishTranslateUp() {
  console.log("translate up");
  modeMsg.mode = 5
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0.05
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}

function publishTranslateDown() {
  console.log("translate down");
  modeMsg.mode = 5
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = -0.05
  modeMsg.yaw_velocity = 0
  modepub.publish(modeMsg);
}


function publishYawLeft() {
  console.log("yaw left");
  modeMsg.mode = 5
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = -50
  modepub.publish(modeMsg);
}

function publishYawRight() {
  console.log("yaw right");
  modeMsg.mode = 5
  modeMsg.x_velocity = 0
  modeMsg.y_velocity = 0
  modeMsg.z_velocity = 0
  modeMsg.yaw_velocity = 50
  modepub.publish(modeMsg);
}

$(document).keydown(function(event){
  var char = String.fromCharCode(event.which || event.keyCode);
  // console.log("Key down: " + char);
  if (char == 'J') {
    publishTranslateLeft();
  } else if (char == 'L') {
    publishTranslateRight();
  } else if (char == "K") {
    publishTranslateBackward();
  } else if (char == "I") {
    publishTranslateForward();
  } else if (char == "W") {
    publishTranslateUp();
  } else if (char == "S") {
    publishTranslateDown();
  } else if (char == "A") {
    publishYawLeft();
  } else if (char == "D") {
    publishYawRight();
  } else {
    //console.log('undefined key: ' + event.keyCode);
  }
});

var irChart;
var count;
var windowSize;
$(document).ready(function() {
    var ctx = document.getElementById("irChart").getContext('2d');
    count = 0;
    windowSize = 500;
    irChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array(windowSize),
            datasets: [
              {
                label: 'IR Readings',
                data: Array(windowSize),
                borderWidth: 1,
                pointRadius: 0,
                //borderColor: 'rgba(0, 255, 0, 1)'
              },
              {
                label: 'Window',
                data: Array(windowSize),
                borderWidth: 1,
                pointRadius: 0,
                borderColor: 'rgba(255, 0, 0, 1)'
              },
            ]
        },
        options: {
            animation: {
               duration: 0,
            },
            scales: {
                yAxes: [{
                    ticks: {
                        beginAtZero:true,
                        min: 0,
                        max: 0.6,
                    }
                }],
                xAxes: [{
                    display: false
                }]
            },
            legend: {
              display: false
            },
        }
    });
    for (i = 0; i < irChart.data.datasets[0].data.length; i++) {
      irChart.data.datasets[0].data[i] = 0;
      irChart.data.labels[i] = i;
      irChart.data.datasets[1].data[i] = 0;
    }
    init();
});

$(window).on("beforeunload", function(e) {
    closeSession();
});


$(document).keyup(function(event){
  var char = String.fromCharCode(event.which || event.keyCode);
  if (char == "J" || char == "L" || char == "K" || char == "I" || char == "W" || char == "S" || char == "A" || char == "D") {
    publishZeroVelocity();
  }
});

$(document).keypress(function(event){
  var char = String.fromCharCode(event.which || event.keyCode);
  if (char == ';') {
    publishArm();
  } else if (char == ' ') {
    publishDisarm();
  } else if (char == 'h') {
    publishZeroVelocity();
  } else if (char == 'r') {
    publishResetTransform();
  } else if (char == 't') {
    publishTakeoff();
  } else if (char == 'p') {
    publishToggleTransform();
  }
});